"""Usage limits per plan. The rule that matters: CHECK AND CONSUME in ONE atomic step.

A separate "is there quota left?" followed by "use it" lets two simultaneous requests both pass the check.
The in-memory ledger below uses a lock; the Django version (docuask/usage.py) does the same with one conditional UPDATE.
"""
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple


@dataclass(frozen=True)
class Plan:
    name: str
    max_documents: int
    pages_per_month: int
    questions_per_month: int
    max_file_mb: int
    max_pages_per_file: int


PLANS: Dict[str, Plan] = {
    "free": Plan("free", max_documents=5, pages_per_month=100, questions_per_month=30, max_file_mb=10, max_pages_per_file=50),
    "pro": Plan("pro", max_documents=200, pages_per_month=5000, questions_per_month=2000, max_file_mb=50, max_pages_per_file=500),
    "business": Plan("business", max_documents=2000, pages_per_month=50000, questions_per_month=20000, max_file_mb=100, max_pages_per_file=1000),
}

MONTHLY_METRICS = {"pages": "pages_per_month", "questions": "questions_per_month"}


class LimitExceeded(Exception):
    def __init__(self, metric: str, limit: int, used: int, resets_at: Optional[datetime]):
        self.metric, self.limit, self.used, self.resets_at = metric, limit, used, resets_at
        when = f" It resets on {resets_at:%Y-%m-%d}." if resets_at else ""
        super().__init__(f"You have reached your plan's limit of {limit} {metric}.{when}")


def period_start(now: datetime) -> datetime:
    now = now.astimezone(timezone.utc)
    return datetime(now.year, now.month, 1, tzinfo=timezone.utc)


def next_reset(now: datetime) -> datetime:
    start = period_start(now)
    return datetime(start.year + (start.month == 12), start.month % 12 + 1, 1, tzinfo=timezone.utc)


class InMemoryLedger:
    """Same contract as the database version, for tests."""

    def __init__(self):
        self._lock = threading.Lock()
        self._used: Dict[Tuple[str, str, datetime], int] = {}

    def try_consume(self, owner: str, metric: str, amount: int, limit: int, period: datetime) -> Optional[int]:
        """Atomically add `amount` unless that would exceed `limit`. Returns the new total, or None if refused."""
        with self._lock:
            key = (owner, metric, period)
            used = self._used.get(key, 0)
            if used + amount > limit:
                return None
            self._used[key] = used + amount
            return used + amount

    def refund(self, owner: str, metric: str, amount: int, period: datetime) -> None:
        with self._lock:
            key = (owner, metric, period)
            self._used[key] = max(0, self._used.get(key, 0) - amount)

    def used(self, owner: str, metric: str, period: datetime) -> int:
        with self._lock:
            return self._used.get((owner, metric, period), 0)


def consume(ledger, owner: str, plan: Plan, metric: str, amount: int = 1, now: Optional[datetime] = None) -> int:
    if amount <= 0:
        raise ValueError("amount must be positive")
    now = now or datetime.now(timezone.utc)
    limit = getattr(plan, MONTHLY_METRICS[metric])
    period = period_start(now)
    total = ledger.try_consume(owner, metric, amount, limit, period)
    if total is None:
        raise LimitExceeded(metric, limit, ledger.used(owner, metric, period), next_reset(now))
    return total


def check_upload(plan: Plan, size_bytes: int, current_documents: int) -> None:
    """Limits that are not monthly counters: checked before the file is stored."""
    if current_documents >= plan.max_documents:
        raise LimitExceeded("documents", plan.max_documents, current_documents, None)
    if size_bytes > plan.max_file_mb * 1024 * 1024:
        raise LimitExceeded(f"MB per file", plan.max_file_mb, size_bytes // (1024 * 1024), None)


def billable_pages(pages) -> int:
    """What a document costs against the monthly "pages" quota. Real pages count as pages; formats without pages
    (Word, plain text) are charged one page per 3,000 characters, so a 400,000-character .txt is not free."""
    numbered = [p for p in pages if p.number is not None]
    if numbered:
        return len(numbered)
    return max(1, -(-sum(len(p.text) for p in pages) // 3000))
