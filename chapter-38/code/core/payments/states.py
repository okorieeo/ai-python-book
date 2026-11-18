"""One payment lifecycle for every gateway."""
from __future__ import annotations

import enum


class PaymentStatus(enum.StrEnum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELED = "canceled"
    PARTIALLY_REFUNDED = "partially_refunded"
    REFUNDED = "refunded"
    DISPUTED = "disputed"


S = PaymentStatus
# Money wins: a late success may follow a failed attempt, but a success is never undone by a "failed" event.
TRANSITIONS: dict[PaymentStatus, frozenset[PaymentStatus]] = {
    S.PENDING: frozenset({S.SUCCEEDED, S.FAILED, S.CANCELED}),
    S.FAILED: frozenset({S.SUCCEEDED, S.CANCELED}),
    S.CANCELED: frozenset({S.SUCCEEDED}),   # customer paid in a window we thought was closed
    S.SUCCEEDED: frozenset({S.PARTIALLY_REFUNDED, S.REFUNDED, S.DISPUTED}),
    S.PARTIALLY_REFUNDED: frozenset({S.PARTIALLY_REFUNDED, S.REFUNDED, S.DISPUTED}),
    S.REFUNDED: frozenset({S.DISPUTED}),
    S.DISPUTED: frozenset({S.SUCCEEDED, S.REFUNDED}),   # dispute won or lost
}
MONEY_HELD = frozenset({S.SUCCEEDED, S.PARTIALLY_REFUNDED, S.DISPUTED})


class InvalidTransition(Exception):
    pass


def can_transition(current: PaymentStatus, new: PaymentStatus) -> bool:
    return new in TRANSITIONS.get(current, frozenset())


def transition(current: PaymentStatus, new: PaymentStatus) -> PaymentStatus:
    if current == new:
        return current          # replaying the same event is harmless
    if not can_transition(current, new):
        raise InvalidTransition(f"{current} -> {new} is not allowed")
    return new
