"""Refund rules that do not depend on which gateway took the money."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from .money import Money
from .states import MONEY_HELD, PaymentStatus


class RefundNotAllowed(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class RefundPolicy:
    window_days: int = 30
    allow_partial: bool = True


def refundable(total: Money, already_refunded: Money) -> Money:
    return total - already_refunded


def validate_refund(*, status: PaymentStatus, paid_at: datetime | None, now: datetime, total: Money,
                    already_refunded: Money, requested: Money, policy: RefundPolicy = RefundPolicy(),
                    staff_override: bool = False) -> Money:
    """Return the amount to refund, or raise RefundNotAllowed with a machine-readable code."""
    if requested.currency != total.currency:
        raise RefundNotAllowed("currency_mismatch", "refund currency must match the payment")
    if status not in MONEY_HELD:
        raise RefundNotAllowed("not_refundable_state", f"a {status} payment cannot be refunded")
    if status == PaymentStatus.DISPUTED:
        raise RefundNotAllowed("disputed", "a disputed payment is settled through the dispute process")
    if not requested.is_positive():
        raise RefundNotAllowed("non_positive", "refund must be greater than zero")
    left = refundable(total, already_refunded)
    if requested.amount_minor > left.amount_minor:
        raise RefundNotAllowed("exceeds_remaining", f"only {left} is left to refund")
    if requested != left and not policy.allow_partial:
        raise RefundNotAllowed("partial_not_allowed", "only full refunds are allowed")
    if paid_at is not None and now - paid_at > timedelta(days=policy.window_days) and not staff_override:
        raise RefundNotAllowed("window_closed", f"the {policy.window_days}-day refund window has closed")
    return requested


def status_after_refund(total: Money, refunded_total: Money) -> PaymentStatus:
    if refunded_total.amount_minor >= total.amount_minor:
        return PaymentStatus.REFUNDED
    return PaymentStatus.PARTIALLY_REFUNDED if refunded_total.amount_minor > 0 else PaymentStatus.SUCCEEDED


def refund_idempotency_key(reference: str, already_refunded: Money, requested: Money) -> str:
    """Same state and same request give the same key, so a retry cannot refund twice."""
    return f"refund:{reference}:{already_refunded.amount_minor}:{requested.amount_minor}"
