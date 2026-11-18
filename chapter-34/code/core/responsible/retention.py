"""Retention rules as data, and the arithmetic to apply them."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable, Iterator, Sequence, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class RetentionRule:
    name: str
    days: int | None  # None = keep until the user deletes it (or the account is deleted)
    why: str

    def __post_init__(self):
        if self.days is not None and self.days <= 0:
            raise ValueError("days must be positive, or None to keep until deletion")


RULES = {
    "messages": RetentionRule("messages", None, "The product: the user's own history"),
    "deleted_messages_backup": RetentionRule("deleted_messages_backup", 35, "Backups roll off"),
    "flagged_for_review": RetentionRule("flagged_for_review", 30, "Safety review, then removed"),
    "ai_request_logs": RetentionRule("ai_request_logs", 30, "Debugging and cost tracking (ids and counts only)"),
    "audit_events": RetentionRule("audit_events", 730, "Accountability; holds ids, not content"),
    "invoices": RetentionRule("invoices", 2555, "Tax and accounting law (check your country)"),
    "deletion_requests": RetentionRule("deletion_requests", 1095, "Proof that erasure was done"),
}


def cutoff(now: datetime, days: int) -> datetime:
    return now - timedelta(days=days)


def is_expired(created_at: datetime, days: int | None, now: datetime) -> bool:
    if days is None:
        return False
    return created_at <= cutoff(now, days)


def expired_ids(records: Iterable[tuple[T, datetime]], days: int | None, now: datetime,
                *, legal_hold: frozenset = frozenset()) -> list[T]:
    """Ids whose age is past the rule. Anything under a legal hold is never returned."""
    return [rid for rid, created in records if rid not in legal_hold and is_expired(created, days, now)]


def batched(items: Sequence[T], size: int = 500) -> Iterator[Sequence[T]]:
    if size <= 0:
        raise ValueError("size must be positive")
    for i in range(0, len(items), size):
        yield items[i:i + size]
