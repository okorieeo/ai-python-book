"""Celery jobs (Chapter 15): reminders every minute, daily briefings every five."""
import logging
from datetime import timedelta

import requests
from celery import shared_task
from django.db import IntegrityError
from django.db.models import Q
from django.utils import timezone

from core.timeutils import get_zone, local_day_bounds, to_local
from schedule.models import Event, PlannerPreferences
from schedule.recurrence import RuleError, expand, parse_rule
from schedule.services import occurrences_between
from tasks.models import Task
from tasks.planning import PlannableTask, rank_tasks

from .briefing import ReminderCandidate, due_reminders, is_briefing_due, render_briefing
from .models import SentNotification
from .notify import send_push

log = logging.getLogger(__name__)
LOOKAHEAD = timedelta(days=1)  # the longest reminder we allow is 24 hours before


def _claim(user, kind: str, key: str) -> SentNotification | None:
    """Insert the (user, kind, key) row. The unique constraint means exactly one worker
    wins, even on retries."""
    try:
        return SentNotification.objects.create(user=user, kind=kind, key=key)
    except IntegrityError:
        return None


def _deliver(claim: SentNotification, user, *, title: str, body: str, data: dict) -> None:
    try:
        send_push(user, title=title, body=body, data=data)
    except requests.RequestException:
        log.warning("push_failed", extra={"kind": claim.kind})
        # release the claim: the next tick tries again, until the catch-up window closes
        claim.delete()


@shared_task
def send_due_reminders() -> None:
    now = timezone.now()
    candidates, owners = [], {}
    soon = Q(recurrence__isnull=True, start_at__gte=now, start_at__lt=now + LOOKAHEAD)
    # started any time before: expanded below
    repeating = Q(recurrence__isnull=False, start_at__lt=now + LOOKAHEAD)
    for event in Event.objects.filter(soon | repeating, remind_minutes_before__isnull=False).select_related("user").iterator():
        tz = get_zone(event.timezone)
        if event.recurrence:
            try:
                occs = expand(parse_rule(event.recurrence), first_start=event.start_at.astimezone(tz).replace(tzinfo=None),
                              duration=event.end_at - event.start_at, tz=tz, window_start=now, window_end=now + LOOKAHEAD)
            except RuleError:
                continue
            starts = [o.start for o in occs]
        else:
            starts = [event.start_at] if now <= event.start_at < now + LOOKAHEAD else []
        for start in starts:
            candidates.append(ReminderCandidate(str(event.public_id), event.title, start, event.remind_minutes_before))
        owners[str(event.public_id)] = event.user
    for due in due_reminders(candidates, now=now):
        user = owners[due.event_id]
        claim = _claim(user, "event_reminder", due.key)
        if claim:
            _deliver(claim, user, title=due.title, body=f"Starts in {due.minutes_before} minutes",
                     data={"screen": "calendar", "event_id": due.event_id})

    window = timedelta(minutes=15)
    for task in Task.objects.filter(remind_at__lte=now, remind_at__gt=now - window).exclude(status=Task.Status.DONE).select_related("user"):
        claim = _claim(task.user, "task_reminder", f"{task.public_id}:{task.remind_at.isoformat()}")
        if claim:
            _deliver(claim, task.user, title="Reminder", body=task.title, data={"screen": "tasks", "task_id": str(task.public_id)})


@shared_task
def send_daily_briefings() -> None:
    now = timezone.now()
    for prefs in PlannerPreferences.objects.filter(briefing_enabled=True).select_related("user").iterator():
        tz = get_zone(prefs.timezone)
        today = to_local(now, tz).date()
        if not is_briefing_due(now=now, tz=tz, send_at=prefs.briefing_time, last_sent=prefs.last_briefing_on):
            continue
        # Claim the day with one conditional UPDATE: it returns 1 for exactly one
        # worker.
        claimed = PlannerPreferences.objects.filter(pk=prefs.pk).exclude(last_briefing_on=today).update(last_briefing_on=today)
        if not claimed:
            continue
        start, end = local_day_bounds(today, tz)
        events = [(o.start, o.end, o.event.title) for o in occurrences_between(user=prefs.user, start=start, end=end)]
        open_tasks = list(Task.objects.filter(user=prefs.user).exclude(status=Task.Status.DONE)[:100])
        ranked = rank_tasks([PlannableTask(str(t.public_id), t.title, t.priority, t.due_at, t.estimate_minutes, t.created_at)
                             for t in open_tasks], now=now, tz=tz)
        title, body = render_briefing(events=events, ranked=ranked, tz=tz)
        try:
            send_push(prefs.user, title=title, body=body, data={"screen": "today"})
        except requests.RequestException:
            PlannerPreferences.objects.filter(pk=prefs.pk).update(last_briefing_on=prefs.last_briefing_on)  # try again next tick
