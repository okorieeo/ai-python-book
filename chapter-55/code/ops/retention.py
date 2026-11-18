"""Which backups to keep: the newest of each of the last N days, ISO weeks and months.

Pure functions, standard library only. Files are named  chat-YYYYmmdd-HHMMSS.dump.age;
anything else in the folder is never touched (and the newest backup is never deleted).
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta

NAME = re.compile(r"^(?P<prefix>[A-Za-z0-9_-]+)-(?P<stamp>\d{8}-\d{6})\.dump(\.age)?$")


def parse_stamp(filename: str) -> datetime | None:
    match = NAME.match(filename)
    return datetime.strptime(match.group("stamp"), "%Y%m%d-%H%M%S") if match else None


def _months_back(today: date, n: int) -> tuple[int, int]:
    index = today.year * 12 + (today.month - 1) - n
    return index // 12, index % 12 + 1


def select_keep(stamps: list[datetime], today: date, daily: int = 7, weekly: int = 4, monthly: int = 6) -> set[datetime]:
    keep: set[datetime] = set()
    if not stamps:
        return keep
    newest = lambda items: max(items) if items else None  # noqa: E731
    for i in range(daily):
        day = today - timedelta(days=i)
        pick = newest([s for s in stamps if s.date() == day])
        if pick:
            keep.add(pick)
    this_week = today - timedelta(days=today.weekday())
    for i in range(weekly):
        start = this_week - timedelta(weeks=i)
        pick = newest([s for s in stamps if start <= s.date() < start + timedelta(days=7)])
        if pick:
            keep.add(pick)
    for i in range(monthly):
        year, month = _months_back(today, i)
        pick = newest([s for s in stamps if (s.year, s.month) == (year, month)])
        if pick:
            keep.add(pick)
    keep.add(max(stamps))
    return keep


def plan_prune(filenames: list[str], today: date, daily: int = 7, weekly: int = 4, monthly: int = 6):
    """Return (keep, delete) filename lists. Unrecognised names go in neither list."""
    parsed = {name: parse_stamp(name) for name in filenames}
    known = {name: stamp for name, stamp in parsed.items() if stamp}
    keep_stamps = select_keep(list(known.values()), today, daily, weekly, monthly)
    keep = sorted(n for n, s in known.items() if s in keep_stamps)
    delete = sorted(n for n, s in known.items() if s not in keep_stamps)
    return keep, delete
