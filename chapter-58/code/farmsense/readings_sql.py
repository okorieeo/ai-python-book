"""Raw SQL for readings: bulk insert that ignores duplicates, and bucketed queries for charts."""
from datetime import datetime
from typing import Dict, Iterable, List, Sequence, Tuple

from django.db import connection

from farmsense_core.ingest import Reading


def insert_readings(sensor_ids: Dict[str, int], readings: Iterable[Reading]) -> int:
    """One statement for the whole batch. A device that resends a batch after a timeout creates no duplicates
    because the primary key is (sensor, timestamp) and ON CONFLICT DO NOTHING ignores the second copy."""
    rows = [(sensor_ids[r.sensor_key], r.ts, r.value) for r in readings]
    if not rows:
        return 0
    with connection.cursor() as cur:
        cur.executemany("INSERT INTO farmsense_reading (sensor_id, ts, value) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING", rows)
        return cur.rowcount


def bucketed(sensor_id: int, start: datetime, end: datetime, bucket_seconds: int) -> List[Tuple[datetime, int, float, float, float]]:
    """Charts never ask for raw points: a month of one-minute data is 43,200 of them. Ask for ~300 buckets instead."""
    with connection.cursor() as cur:
        cur.execute(
            "SELECT date_bin(make_interval(secs => %s), ts, TIMESTAMPTZ '2000-01-01') AS bucket, count(*), avg(value), min(value), max(value) "
            "FROM farmsense_reading WHERE sensor_id = %s AND ts >= %s AND ts < %s GROUP BY bucket ORDER BY bucket",
            [bucket_seconds, sensor_id, start, end])
        return cur.fetchall()


def latest(sensor_ids: Sequence[int]) -> Dict[int, Tuple[datetime, float]]:
    with connection.cursor() as cur:
        cur.execute("SELECT DISTINCT ON (sensor_id) sensor_id, ts, value FROM farmsense_reading WHERE sensor_id = ANY(%s) "
                    "AND ts > now() - interval '1 day' ORDER BY sensor_id, ts DESC", [list(sensor_ids)])
        return {sid: (ts, v) for sid, ts, v in cur.fetchall()}
