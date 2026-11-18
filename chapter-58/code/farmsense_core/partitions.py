"""Monthly PostgreSQL partitions for the readings table. A partition is a separate physical table for one month, so
dropping old data is instant (DROP TABLE) instead of a slow, bloating DELETE, and recent data stays small and fast.
The functions only BUILD the SQL text and decide which partitions to create or drop: running it is the Celery task's job."""
import re
from datetime import date
from typing import Iterable, List

TABLE = "farmsense_reading"
_NAME = re.compile(rf"^{TABLE}_(\d{{4}})_(\d{{2}})$")


def month_start(year: int, month: int) -> date:
    return date(year, month, 1)


def add_months(d: date, n: int) -> date:
    index = d.year * 12 + (d.month - 1) + n
    return date(index // 12, index % 12 + 1, 1)


def partition_name(d: date) -> str:
    return f"{TABLE}_{d.year:04d}_{d.month:02d}"


def partition_ddl(d: date) -> str:
    start, end = month_start(d.year, d.month), add_months(d, 1)
    return (f"CREATE TABLE IF NOT EXISTS {partition_name(d)} PARTITION OF {TABLE} "
            f"FOR VALUES FROM ('{start.isoformat()}') TO ('{end.isoformat()}')")


def partitions_to_create(today: date, ahead: int = 2) -> List[str]:
    """This month and the next `ahead` months, so an outage of the maintenance job never leaves a day without a partition."""
    first = month_start(today.year, today.month)
    return [partition_ddl(add_months(first, i)) for i in range(ahead + 1)]


def partitions_to_drop(existing: Iterable[str], today: date, keep_months: int) -> List[str]:
    """Partitions entirely older than the retention window. Names that do not match our pattern are never touched."""
    cutoff = add_months(month_start(today.year, today.month), -keep_months)
    out = []
    for name in existing:
        m = _NAME.match(name)
        if m and month_start(int(m.group(1)), int(m.group(2))) < cutoff:
            out.append(name)
    return sorted(out)


CREATE_PARENT_SQL = f"""
CREATE TABLE {TABLE} (
    sensor_id   bigint           NOT NULL,
    ts          timestamptz      NOT NULL,
    value       double precision NOT NULL,
    received_at timestamptz      NOT NULL DEFAULT now(),
    PRIMARY KEY (sensor_id, ts)
) PARTITION BY RANGE (ts);
CREATE TABLE {TABLE}_default PARTITION OF {TABLE} DEFAULT;
"""
