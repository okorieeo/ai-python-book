"""When to send a daily briefing, which reminders are due, and what the briefing says.
Pure Python, no Django.

Deliberately NOT written by the model: it is predictable, free, and cannot be tricked by
the text of a task.
"""
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Sequence
from zoneinfo import ZoneInfo

from core.timeutils import resolve_local, to_local
from tasks.planning import RankedTask

MAX_BODY_CHARS = 240


def is_briefing_due(
    *, now: datetime, tz: ZoneInfo, send_at: time, last_sent: date | None, max_late: timedelta = timedelta(hours=3)
) -> bool:
    """True once, each local day, from `send_at` until `max_late` later.

    The job runs every few minutes, so "due" must be a RANGE, not an exact minute (a
    tick may be missed),
    but not unbounded (a 07:30 briefing is useless at nine at night).
    """
    today = to_local(now, tz).date()
    if last_sent is not None and last_sent >= today:
        return False
    scheduled = resolve_local(datetime.combine(today, send_at), tz).utc
    return scheduled <= now < scheduled + max_late


@dataclass(frozen=True)
class ReminderCandidate:
    event_id: str
    title: str
    start: datetime          # aware UTC: this occurrence's start
    minutes_before: int


@dataclass(frozen=True)
class DueReminder:
    # unique per event occurrence: the database refuses to send the same key twice
    key: str
    event_id: str
    title: str
    start: datetime
    minutes_before: int


def due_reminders(
    candidates: Sequence[ReminderCandidate], *, now: datetime, catchup: timedelta = timedelta(minutes=15)
) -> list[DueReminder]:
    """Reminders whose time has come, but only recent ones: after downtime we do not
    replay old news."""
    due = []
    for c in candidates:
        fire_at = c.start - timedelta(minutes=c.minutes_before)
        if now - catchup < fire_at <= now and c.start > now:
            due.append(DueReminder(f"{c.event_id}:{c.start.isoformat()}", c.event_id, c.title, c.start, c.minutes_before))
    return sorted(due, key=lambda d: d.start)


def render_briefing(
    *, events: Sequence[tuple[datetime, datetime, str]], ranked: Sequence[RankedTask], tz: ZoneInfo, max_tasks: int = 3
) -> tuple[str, str]:
    """Return (title, body) for a push notification."""
    events = sorted(events, key=lambda e: e[0])
    tasks = list(ranked)[:max_tasks]
    if not events and not tasks:
        return "Good morning", "Nothing scheduled today. A clear day."
    noun = "event" if len(events) == 1 else "events"
    title = f"Today: {len(events)} {noun}, {len(ranked)} open task{'s' if len(ranked) != 1 else ''}"
    parts = []
    if events:
        parts.append("; ".join(f"{to_local(start, tz):%H:%M} {name}" for start, _end, name in events[:4]))
    if tasks:
        parts.append("First: " + ", ".join(r.task.title for r in tasks))
    body = ". ".join(parts)
    if len(body) > MAX_BODY_CHARS:
        body = body[: MAX_BODY_CHARS - 1].rstrip() + "…"
    return title, body
