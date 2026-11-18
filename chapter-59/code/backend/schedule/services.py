"""Business rules for the calendar: events, repeats, conflicts, free time and
preferences."""
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.db import transaction

from audit.services import Action, record
from core.security.sanitize import clean_text
from core.timeutils import TimeInputError, get_zone, resolve_local

from .availability import Interval, WorkingHours, find_conflicts
from .models import Event, PlannerPreferences
from .recurrence import RuleError, expand, parse_rule

MAX_WINDOW = timedelta(days=400)
MAX_REPEATING_EVENTS_PER_QUERY = 500


class EventValidationError(ValueError):
    pass


@dataclass(frozen=True)
class EventOccurrence:
    event: Event
    start: datetime   # aware UTC
    end: datetime
    recurring: bool


# ---- preferences
# -------------------------------------------------------------------------------

def get_preferences(user) -> PlannerPreferences:
    prefs, _ = PlannerPreferences.objects.get_or_create(user=user)
    return prefs


def user_zone(user) -> ZoneInfo:
    try:
        return get_zone(get_preferences(user).timezone)
    except TimeInputError:
        # a broken stored value must not take the whole calendar down
        return get_zone("UTC")


def working_hours(prefs: PlannerPreferences) -> WorkingHours:
    return WorkingHours(prefs.work_start, prefs.work_end, frozenset(prefs.work_days))


def set_timezone(*, user, name: str) -> PlannerPreferences:
    get_zone(name)  # raises TimeInputError for anything that is not a real zone
    prefs = get_preferences(user)
    prefs.timezone = name
    prefs.save(update_fields=["timezone"])
    return prefs


# ---- reading
# -----------------------------------------------------------------------------------

def get_event_for_user(*, user, public_id) -> Event:
    return Event.objects.get(user=user, public_id=public_id)


def occurrences_between(*, user, start: datetime, end: datetime, ignore: Event | None = None) -> list[EventOccurrence]:
    """Every occurrence overlapping [start, end), repeats expanded, earliest first."""
    if end <= start or end - start > MAX_WINDOW:
        raise EventValidationError("The time range must be positive and at most 400 days.")
    base = Event.objects.filter(user=user)
    if ignore is not None:
        base = base.exclude(pk=ignore.pk)
    found = [
        EventOccurrence(e, e.start_at, e.end_at, False)
        for e in base.filter(recurrence__isnull=True, start_at__lt=end, end_at__gt=start)
    ]
    for e in base.filter(recurrence__isnull=False, start_at__lt=end)[:MAX_REPEATING_EVENTS_PER_QUERY]:
        tz = get_zone(e.timezone)
        try:
            rule = parse_rule(e.recurrence)
            first_local = e.start_at.astimezone(tz).replace(tzinfo=None)
            for occ in expand(rule, first_start=first_local, duration=e.end_at - e.start_at, tz=tz,
                              window_start=start, window_end=end):
                found.append(EventOccurrence(e, occ.start, occ.end, True))
        except RuleError:
            continue  # one broken rule must not hide the rest of the calendar
    return sorted(found, key=lambda o: (o.start, o.event.id))


def busy_intervals(*, user, start: datetime, end: datetime) -> list[Interval]:
    return [Interval(o.start, o.end) for o in occurrences_between(user=user, start=start, end=end)]


# ---- writing
# -----------------------------------------------------------------------------------

def _validated_times(start_local: datetime, end_local: datetime, tz: ZoneInfo) -> tuple[datetime, datetime]:
    start = resolve_local(start_local, tz).utc
    end = resolve_local(end_local, tz).utc
    if end <= start:
        raise EventValidationError("end: must be after start")
    if end - start > timedelta(days=1):
        raise EventValidationError("end: events longer than 24 hours are not supported")
    return start, end


def _conflicts(user, start: datetime, end: datetime, ignore: Event | None = None) -> list[EventOccurrence]:
    window = occurrences_between(user=user, start=start - timedelta(days=1), end=end + timedelta(days=1), ignore=ignore)
    mine = Interval(start, end)
    clashing = find_conflicts(mine, [Interval(o.start, o.end) for o in window])
    return [o for o in window if Interval(o.start, o.end) in clashing]


def create_event(
    *, user, tz: ZoneInfo, title: str, start_local: datetime, end_local: datetime, description: str = "",
    location: str = "", recurrence: dict | None = None, remind_minutes_before: int | None = None,
) -> tuple[Event, list[EventOccurrence]]:
    """Create an event. Returns it with the existing events it overlaps: a warning, not
    an error."""
    try:
        title = clean_text(title, max_length=200, single_line=True)
        description = clean_text(description or "", max_length=4000)
        location = clean_text(location or "", max_length=200, single_line=True)
    except ValueError as exc:
        raise EventValidationError(str(exc)) from exc
    if not title:
        raise EventValidationError("title: must not be empty")
    if remind_minutes_before is not None and not 0 <= remind_minutes_before <= 1440:
        raise EventValidationError("remind_minutes_before: must be 0 to 1440")
    if recurrence is not None:
        try:
            parse_rule(recurrence)
        except RuleError as exc:
            raise EventValidationError(f"recurrence: {exc}") from exc
    start, end = _validated_times(start_local, end_local, tz)
    clashes = _conflicts(user, start, end)
    event = Event.objects.create(
        user=user, title=title, description=description, location=location, start_at=start, end_at=end,
        timezone=tz.key, recurrence=recurrence, remind_minutes_before=remind_minutes_before,
    )
    return event, clashes


def reschedule_event(
    *, user, tz: ZoneInfo, event: Event, start_local: datetime, end_local: datetime | None = None
) -> tuple[Event, list[EventOccurrence]]:
    if event.user_id != user.id:
        raise Event.DoesNotExist
    if event.recurrence:
        raise EventValidationError("This event repeats. Ask the person how to change the series; it cannot be moved here.")
    duration = event.end_at - event.start_at
    start = resolve_local(start_local, tz).utc
    end = resolve_local(end_local, tz).utc if end_local is not None else start + duration
    if end <= start:
        raise EventValidationError("end: must be after start")
    clashes = _conflicts(user, start, end, ignore=event)
    event.start_at, event.end_at, event.timezone = start, end, tz.key
    event.save(update_fields=["start_at", "end_at", "timezone", "updated_at"])
    return event, clashes


def delete_event(*, user, event: Event, request=None) -> None:
    if event.user_id != user.id:
        raise Event.DoesNotExist
    with transaction.atomic():
        record(Action.EVENT_DELETED, request=request, actor=user, target=event,
               metadata={"recurring": bool(event.recurrence)})
        event.delete()
