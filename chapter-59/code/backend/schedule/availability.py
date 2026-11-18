"""Conflicts and free time. Pure Python, no Django.

Everything here works on half-open intervals [start, end): a meeting that ends at 10:00
does NOT
conflict with one that starts at 10:00.
"""
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Iterable
from zoneinfo import ZoneInfo

from core.timeutils import resolve_local, to_local

MAX_SEARCH_DAYS = 62


@dataclass(frozen=True)
class Interval:
    start: datetime  # aware
    end: datetime    # aware

    def __post_init__(self):
        if self.start.tzinfo is None or self.end.tzinfo is None:
            raise ValueError("Intervals need timezone-aware datetimes.")
        if self.end <= self.start:
            raise ValueError("An interval must end after it starts.")

    @property
    def duration(self) -> timedelta:
        return self.end - self.start


@dataclass(frozen=True)
class WorkingHours:
    start: time = time(9, 0)
    end: time = time(17, 0)
    weekdays: frozenset[int] = frozenset({0, 1, 2, 3, 4})  # Monday=0 ... Sunday=6

    def __post_init__(self):
        if self.end <= self.start:
            raise ValueError("Working hours must end after they start (overnight shifts are not supported).")


def overlaps(a: Interval, b: Interval) -> bool:
    return a.start < b.end and b.start < a.end


def find_conflicts(candidate: Interval, busy: Iterable[Interval]) -> list[Interval]:
    return sorted((b for b in busy if overlaps(candidate, b)), key=lambda b: b.start)


def merge_intervals(items: Iterable[Interval]) -> list[Interval]:
    """Combine overlapping or touching intervals into the smallest sorted list that
    covers the same time."""
    merged: list[Interval] = []
    for item in sorted(items, key=lambda i: (i.start, i.end)):
        if merged and item.start <= merged[-1].end:
            if item.end > merged[-1].end:
                merged[-1] = Interval(merged[-1].start, item.end)
        else:
            merged.append(item)
    return merged


def free_slots(
    busy: Iterable[Interval],
    *,
    window_start: datetime,
    window_end: datetime,
    duration: timedelta,
    tz: ZoneInfo,
    hours: WorkingHours = WorkingHours(),
    buffer: timedelta = timedelta(0),
) -> list[Interval]:
    """Return the free gaps of at least `duration` inside working hours, earliest first.

    Pass window_start=now so that nothing in the past is offered. `buffer` keeps a
    margin
    around every busy block (travel time, a breather).
    """
    if duration <= timedelta(0):
        raise ValueError("duration must be positive.")
    if window_end <= window_start:
        raise ValueError("The window must end after it starts.")
    first_day = to_local(window_start, tz).date()
    last_day = to_local(window_end, tz).date()
    if (last_day - first_day).days > MAX_SEARCH_DAYS:
        raise ValueError(f"Search at most {MAX_SEARCH_DAYS} days at a time.")

    blocks = merge_intervals(Interval(b.start - buffer, b.end + buffer) for b in busy)
    slots: list[Interval] = []
    day = first_day
    while day <= last_day:
        if day.weekday() in hours.weekdays:
            opens = max(resolve_local(datetime.combine(day, hours.start), tz).utc, window_start)
            closes = min(resolve_local(datetime.combine(day, hours.end), tz).utc, window_end)
            cursor = opens
            for block in blocks:
                if block.end <= cursor:
                    continue
                if block.start >= closes:
                    break
                if block.start - cursor >= duration:
                    slots.append(Interval(cursor, block.start))
                cursor = max(cursor, block.end)
            if closes - cursor >= duration:
                slots.append(Interval(cursor, closes))
        day += timedelta(days=1)
    return slots
