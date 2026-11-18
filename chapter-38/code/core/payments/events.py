"""Apply a normalized webhook event to our payment record. Same code for every gateway."""
from __future__ import annotations

from datetime import datetime
from typing import Protocol

from .checkout import PaymentRecord
from .gateway import EventType, NormalizedEvent
from .money import Money
from .refunds import status_after_refund
from .states import InvalidTransition, PaymentStatus, transition


class Repo(Protocol):
    def get(self, reference: str) -> PaymentRecord | None: ...
    def save(self, record: PaymentRecord) -> None: ...


def apply_event(event: NormalizedEvent, repo: Repo, *, now: datetime) -> str:
    """Return a short outcome code. Raising is reserved for bugs; business surprises are outcomes."""
    if event.type == EventType.IGNORED:
        return "ignored"
    payment = repo.get(event.reference) if event.reference else None
    if payment is None:
        return "unknown_reference"              # keep the raw event; reconciliation will surface it

    if event.type == EventType.PAYMENT_SUCCEEDED:
        if event.amount_minor != payment.amount.amount_minor or event.currency != payment.amount.currency:
            return "amount_mismatch"            # never grant access for the wrong amount
        if payment.status in (PaymentStatus.SUCCEEDED, PaymentStatus.PARTIALLY_REFUNDED, PaymentStatus.REFUNDED):
            return "already_applied"
        payment.status, payment.paid_at = transition(payment.status, PaymentStatus.SUCCEEDED), now
        repo.save(payment)
        return "fulfilled"

    if event.type == EventType.PAYMENT_FAILED:
        if payment.status == PaymentStatus.PENDING:
            payment.status = transition(payment.status, PaymentStatus.FAILED)
            repo.save(payment)
            return "failed"
        return "late_failure_ignored"           # a success (or later state) outranks a failure

    if event.type == EventType.REFUND_UPDATED:
        if event.amount_minor is None:
            return "ignored"
        total_refunded = event.amount_minor if event.amount_is_cumulative else payment.refunded_minor + event.amount_minor
        total_refunded = min(total_refunded, payment.amount.amount_minor)
        if total_refunded <= payment.refunded_minor:
            return "already_applied"
        payment.refunded_minor = total_refunded
        new = status_after_refund(payment.amount, Money(total_refunded, payment.amount.currency))
        try:
            payment.status = transition(payment.status, new)
        except InvalidTransition:
            return "refund_on_unpaid_payment"
        repo.save(payment)
        return "refund_recorded"

    if event.type == EventType.DISPUTE_OPENED:
        payment.status = transition(payment.status, PaymentStatus.DISPUTED)
        repo.save(payment)
        return "disputed"

    return "no_action"
