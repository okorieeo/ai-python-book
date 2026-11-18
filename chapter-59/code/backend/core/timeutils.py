"""Time helpers for a calendar app: the one place that turns local wall-clock time into
UTC.

Rules the whole app follows:
  * the database stores UTC (timezone-aware datetimes);
  * people, and the AI model, talk in LOCAL time ("2026-11-12T15:00" in the user's
    zone);
  * every conversion between the two goes through resolve_local() or to_local().
"""
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

UTC = timezone.utc

# Local time WITHOUT any offset or "Z": models are unreliable at offset arithmetic, so
# we never ask for it.
_LOCAL_DATETIME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?$")
_LOCAL_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class TimeInputError(ValueError):
    """A time value from a user or a model is not in the format we accept."""


def get_zone(name: str) -> ZoneInfo:
    """Return the IANA zone called `name` ("Africa/Lagos"), or raise TimeInputError."""
    if not isinstance(name, str) or not name or len(name) > 64:
        raise TimeInputError("Time zone must be an IANA name such as Africa/Lagos.")
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, OSError) as exc:
        raise TimeInputError(f"Unknown time zone: {name!r}.") from exc


def parse_local_datetime(text: str) -> datetime:
    """'2026-03-08T14:30' -> naive datetime. Offsets and 'Z' are rejected on purpose."""
    value = text.strip() if isinstance(text, str) else ""
    if not _LOCAL_DATETIME.match(value):
        raise TimeInputError(
            f"Expected local time like 2026-03-08T14:30 with no time zone offset; got {text!r}."
        )
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:  # e.g. month 13
        raise TimeInputError(f"{text!r} is not a real date and time.") from exc


def parse_local_date(text: str) -> date:
    value = text.strip() if isinstance(text, str) else ""
    if not _LOCAL_DATE.match(value):
        raise TimeInputError(f"Expected a date like 2026-03-08; got {text!r}.")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise TimeInputError(f"{text!r} is not a real date.") from exc


@dataclass(frozen=True)
class ResolvedTime:
    utc: datetime     # timezone-aware, in UTC
    # the wall-clock time did not exist (clocks jumped forward) and was moved later
    shifted: bool
    # the wall-clock time happened twice (clocks went back); the first one was used
    ambiguous: bool


def resolve_local(naive: datetime, tz: ZoneInfo) -> ResolvedTime:
    """Turn a local wall-clock time into UTC, with an explicit rule for daylight-saving
    edge cases.

    * Gap (spring forward): 02:30 does not exist on that day. We move it forward by the
      size
      of the gap (to 03:30), which is what phone calendars do.
    * Fold (fall back): 01:30 happens twice. We use the first one.
    """
    if naive.tzinfo is not None:
        raise TimeInputError("resolve_local() needs a naive local datetime.")
    first = naive.replace(tzinfo=tz, fold=0)   # fold=0: offset from BEFORE a transition
    second = naive.replace(tzinfo=tz, fold=1)  # fold=1: offset from AFTER a transition
    before, after = first.utcoffset(), second.utcoffset()
    return ResolvedTime(
        utc=first.astimezone(UTC),
        shifted=before < after,    # offset grows at a gap
        ambiguous=before > after,  # offset shrinks at a fold
    )


def to_local(moment: datetime, tz: ZoneInfo) -> datetime:
    if moment.tzinfo is None:
        raise TimeInputError("to_local() needs an aware datetime.")
    return moment.astimezone(tz)


def local_day_bounds(day: date, tz: ZoneInfo) -> tuple[datetime, datetime]:
    """UTC start (inclusive) and end (exclusive) of one local calendar day. A DST day is
    23 or 25 hours."""
    start = resolve_local(datetime.combine(day, time.min), tz).utc
    end = resolve_local(datetime.combine(day + timedelta(days=1), time.min), tz).utc
    return start, end


def format_local(moment: datetime, tz: ZoneInfo) -> str:
    """The format we send to the model and accept back: 2026-11-12T15:00 (local, no
    offset)."""
    return to_local(moment, tz).strftime("%Y-%m-%dT%H:%M")


def describe_local(moment: datetime, tz: ZoneInfo) -> str:
    """Human-friendly: 'Thu 12 Nov 2026, 15:00'."""
    return to_local(moment, tz).strftime("%a %d %b %Y, %H:%M")
