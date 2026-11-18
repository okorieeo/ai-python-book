"""Validate a batch of readings sent by a device. Never trust the device: reject what is wrong, keep what is right,
and tell the device exactly what happened to each reading so that it can stop resending garbage."""
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from .sensors import normalize_value

MAX_BATCH = 500
LATE_AFTER = timedelta(minutes=10)      # older than this: store it, but it must not trigger real-time alerts


@dataclass(frozen=True)
class Reading:
    sensor_key: str
    ts: datetime
    value: float
    late: bool = False


@dataclass(frozen=True)
class Rejection:
    index: int
    reason: str


@dataclass
class BatchResult:
    accepted: List[Reading] = field(default_factory=list)
    rejected: List[Rejection] = field(default_factory=list)

    def summary(self) -> dict:
        reasons: Dict[str, int] = {}
        for r in self.rejected:
            reasons[r.reason] = reasons.get(r.reason, 0) + 1
        return {"accepted": len(self.accepted), "rejected": len(self.rejected), "reasons": reasons}


def parse_timestamp(raw) -> datetime:
    """ISO 8601 WITH a time zone, or Unix seconds (milliseconds are recognised). A time without a zone is ambiguous: refused."""
    if isinstance(raw, bool):
        raise ValueError("bad_timestamp")
    if isinstance(raw, (int, float)):
        seconds = raw / 1000.0 if raw > 1e12 else float(raw)
        try:
            return datetime.fromtimestamp(seconds, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            raise ValueError("bad_timestamp")
    if isinstance(raw, str):
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            raise ValueError("bad_timestamp")
        if dt.tzinfo is None:
            raise ValueError("bad_timestamp")
        return dt.astimezone(timezone.utc)
    raise ValueError("bad_timestamp")


def parse_batch(payload: dict, known_sensors: Dict[str, str], now: Optional[datetime] = None,
                max_future: timedelta = timedelta(minutes=5), max_age: timedelta = timedelta(days=7)) -> BatchResult:
    """known_sensors maps the sensor keys that belong to THIS device to their type. A device can only write to its own sensors."""
    now = now or datetime.now(timezone.utc)
    result = BatchResult()
    items = payload.get("readings") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        raise ValueError("readings must be a list")
    if len(items) > MAX_BATCH:
        raise ValueError(f"at most {MAX_BATCH} readings per request")
    seen = set()
    for i, item in enumerate(items):
        try:
            if not isinstance(item, dict):
                raise ValueError("invalid_value")
            sensor = item.get("sensor")
            stype = known_sensors.get(sensor) if isinstance(sensor, str) else None
            if stype is None:
                raise ValueError("unknown_sensor")
            ts = parse_timestamp(item.get("ts"))
            if ts > now + max_future:
                raise ValueError("in_future")
            if ts < now - max_age:
                raise ValueError("too_old")
            value = normalize_value(stype, item.get("value"), item.get("unit"))
            key = (sensor, ts)
            if key in seen:
                raise ValueError("duplicate_in_batch")
            seen.add(key)
            result.accepted.append(Reading(sensor, ts, value, late=(now - ts) > LATE_AFTER))
        except ValueError as exc:
            result.rejected.append(Rejection(i, str(exc)))
    return result
