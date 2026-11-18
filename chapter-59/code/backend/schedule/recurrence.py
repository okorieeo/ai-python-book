"""Expand a simple recurrence rule into concrete occurrences. Pure Python, no Django.

The rule is a small JSON object stored on the event:

    {"freq": "weekly", "interval": 1, "by_weekday": ["MO", "WE"],
     "until": "2026-12-31", "exclude": ["2026-11-25"]}          # or "count": 10 instead
     of "until"

It is a deliberate subset of the iCalendar (RFC 5545) RRULE. Occurrences keep the same
WALL-CLOCK
time in the event's time zone, so a 09:00 meeting stays at 09:00 when daylight saving
changes.
"""
import itertools
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from core.timeutils import UTC, TimeInputError, parse_local_date, resolve_local

FREQS = ("daily", "weekly", "monthly", "yearly")
WEEKDAYS = ("MO", "TU", "WE", "TH", "FR", "SA", "SU")
_ALLOWED_KEYS = {"freq", "interval", "by_weekday", "until", "count", "exclude"}

MAX_COUNT = 1000          # largest "count" a rule may ask for
MAX_EXCLUDES = 200
# most candidate dates we will look at for one expansion (protects the CPU)
MAX_SCAN = 20_000
MAX_OCCURRENCES = 1000    # most occurrences one expansion may return


class RuleError(ValueError):
    """The recurrence rule is invalid, or too expensive to expand."""


@dataclass(frozen=True)
class Rule:
    freq: str
    interval: int = 1
    by_weekday: tuple[str, ...] = ()
    until: date | None = None
    count: int | None = None
    exclude: frozenset[date] = field(default_factory=frozenset)


@dataclass(frozen=True)
class Occurrence:
    start: datetime      # aware, UTC
    end: datetime        # aware, UTC
    local_date: date     # the calendar date in the event's own time zone


def parse_rule(data: dict) -> Rule:
    """Validate untrusted input (an API body, or arguments the model produced) and
    return a Rule."""
    if not isinstance(data, dict):
        raise RuleError("The recurrence rule must be an object.")
    unknown = set(data) - _ALLOWED_KEYS
    if unknown:
        raise RuleError(f"Unknown recurrence field(s): {', '.join(sorted(unknown))}.")
    freq = data.get("freq")
    if freq not in FREQS:
        raise RuleError(f"freq must be one of: {', '.join(FREQS)}.")
    interval = data.get("interval", 1)
    if isinstance(interval, bool) or not isinstance(interval, int) or not 1 <= interval <= 366:
        raise RuleError("interval must be a whole number from 1 to 366.")

    by_weekday = data.get("by_weekday") or []
    if by_weekday:
        if freq != "weekly":
            raise RuleError("by_weekday can only be used with freq 'weekly'.")
        if (not isinstance(by_weekday, list) or len(by_weekday) > 7
                or any(day not in WEEKDAYS for day in by_weekday)):
            raise RuleError(f"by_weekday must be a list of: {', '.join(WEEKDAYS)}.")

    if data.get("until") is not None and data.get("count") is not None:
        raise RuleError("Use either until or count, not both.")
    until = None
    if data.get("until") is not None:
        try:
            until = parse_local_date(data["until"])
        except TimeInputError as exc:
            raise RuleError(f"until: {exc}") from exc
    count = data.get("count")
    if count is not None and (
        isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= MAX_COUNT
    ):
        raise RuleError(f"count must be a whole number from 1 to {MAX_COUNT}.")

    raw_exclude = data.get("exclude") or []
    if not isinstance(raw_exclude, list) or len(raw_exclude) > MAX_EXCLUDES:
        raise RuleError(f"exclude must be a list of at most {MAX_EXCLUDES} dates.")
    try:
        exclude = frozenset(parse_local_date(item) for item in raw_exclude)
    except TimeInputError as exc:
        raise RuleError(f"exclude: {exc}") from exc

    return Rule(freq, interval, tuple(sorted(set(by_weekday), key=WEEKDAYS.index)), until, count, exclude)


def candidate_dates(rule: Rule, start: date):
    """Yield the dates the rule produces, in order, forever (callers stop early)."""
    if rule.freq == "daily":
        for k in itertools.count():
            yield start + timedelta(days=k * rule.interval)
    elif rule.freq == "weekly":
        indexes = sorted(WEEKDAYS.index(d) for d in rule.by_weekday) or [start.weekday()]
        # the Monday of the first week
        week_one = start - timedelta(days=start.weekday())
        for k in itertools.count():
            monday = week_one + timedelta(weeks=k * rule.interval)
            for index in indexes:
                day = monday + timedelta(days=index)
                if day >= start:
                    yield day
    elif rule.freq == "monthly":
        for k in itertools.count():
            month_index = start.month - 1 + k * rule.interval
            try:
                yield date(start.year + month_index // 12, month_index % 12 + 1, start.day)
            except ValueError:
                # the 31st does not exist in April: iCalendar says skip that month
                continue
    else:  # yearly
        for k in itertools.count():
            try:
                yield date(start.year + k * rule.interval, start.month, start.day)
            except ValueError:
                continue  # 29 February in a non-leap year


def expand(
    rule: Rule,
    *,
    first_start: datetime,        # NAIVE local start of the first occurrence
    duration: timedelta,
    tz: ZoneInfo,
    # aware UTC; occurrences overlapping [window_start, window_end) are returned
    window_start: datetime,
    window_end: datetime,
    max_scan: int = MAX_SCAN,
    limit: int = MAX_OCCURRENCES,
) -> list[Occurrence]:
    if window_end <= window_start:
        raise RuleError("The window must end after it starts.")
    found: list[Occurrence] = []
    try:
        for scanned, day in enumerate(candidate_dates(rule, first_start.date()), start=1):
            if scanned > max_scan:
                raise RuleError("This rule is too expensive to expand for that time range.")
            if rule.count is not None and scanned > rule.count:
                break  # the count includes excluded dates, as in RFC 5545
            if rule.until is not None and day > rule.until:
                break
            start = resolve_local(datetime.combine(day, first_start.time()), tz).utc
            if start >= window_end:
                break  # occurrences only move forward in time
            if day in rule.exclude:
                continue
            end = start + duration
            if end <= window_start:
                continue  # already over before the window began
            found.append(Occurrence(start=start, end=end, local_date=day))
            if len(found) > limit:
                raise RuleError("This rule produces too many occurrences in that time range.")
    except OverflowError:  # walked past the year 9999
        pass
    return found
