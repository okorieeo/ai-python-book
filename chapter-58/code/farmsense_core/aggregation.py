"""Turning thousands of raw readings into something a person can read."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from statistics import median
from typing import List, Sequence, Tuple

Point = Tuple[datetime, float]


@dataclass(frozen=True)
class Bucket:
    start: datetime
    count: int
    avg: float
    minimum: float
    maximum: float


def bucketize(points: Sequence[Point], bucket_seconds: int) -> List[Bucket]:
    """Group points into fixed time buckets (aligned to the Unix epoch, so every chart lines up). Empty buckets are omitted."""
    groups = {}
    for ts, v in points:
        slot = int(ts.timestamp()) // bucket_seconds * bucket_seconds
        groups.setdefault(slot, []).append(v)
    return [Bucket(datetime.fromtimestamp(s, tz=timezone.utc), len(vs), sum(vs) / len(vs), min(vs), max(vs))
            for s, vs in sorted(groups.items())]


def median_filter(values: Sequence[float], window: int = 5) -> List[float]:
    """Replaces each value by the median of its neighbours: a single wild spike disappears, a real trend survives."""
    if window % 2 == 0 or window < 1:
        raise ValueError("window must be odd")
    half = window // 2
    return [median(values[max(0, i - half): i + half + 1]) for i in range(len(values))]


def detect_gaps(timestamps: Sequence[datetime], expected_interval_s: int, factor: float = 3.0) -> List[Tuple[datetime, datetime]]:
    """Periods with no data: a silence longer than `factor` x the normal interval."""
    gaps = []
    for a, b in zip(timestamps, timestamps[1:]):
        if (b - a).total_seconds() > expected_interval_s * factor:
            gaps.append((a, b))
    return gaps


def rate_per_minute(a: Point, b: Point) -> float:
    seconds = (b[0] - a[0]).total_seconds()
    if seconds <= 0:
        return 0.0
    return (b[1] - a[1]) / seconds * 60.0
