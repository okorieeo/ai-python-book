"""Turning a subscription record into a yes or no, the Paystack way.

Stripe tells you 'past_due' when a renewal fails. Paystack does not run a retry schedule for you, so the
useful fact is DATES: a customer has paid up to the next payment date, plus a short grace period.
"""
from dataclasses import dataclass
from typing import Optional

DAY = 86400


@dataclass(frozen=True)
class AccessDecision:
    paid: bool
    tier: str
    reason: str
    until: Optional[int] = None


FREE = AccessDecision(False, "free", "no subscription")


def decide_access(record, now: float, grace_days: int = 3) -> AccessDecision:
    """Decide from Paystack's status and the next payment date.

    active           paid until the next payment date, then a grace period for the renewal to go through
    attention        the last charge failed: still paid until the next payment date, then the grace period
    non-renewing     cancelled, but paid until the next payment date. No grace: it will never be charged
    completed, cancelled, anything else   not paid
    """
    if record is None:
        return FREE
    status, tier, due = record.status, record.tier or "free", record.next_payment_date
    if status in {"active", "attention"}:
        if record.trial_end is not None and now < record.trial_end:
            return AccessDecision(True, tier, "free trial", record.trial_end)
        if due is None:
            return AccessDecision(True, tier, "active")
        grace_end = due + grace_days * DAY
        if now <= due:
            reason = "last renewal failed, update your card" if status == "attention" else "active"
            return AccessDecision(True, tier, reason, due)
        if now <= grace_end:
            return AccessDecision(True, tier, "renewal payment pending, in the grace period", grace_end)
        return AccessDecision(False, "free", "the renewal payment was not received", grace_end)
    if status == "non-renewing":
        if due is not None and now <= due:
            return AccessDecision(True, tier, "cancelled, active until the end of the period", due)
        return AccessDecision(False, "free", "the subscription has ended", due)
    reasons = {"cancelled": "the subscription was cancelled", "completed": "the subscription is complete"}
    return AccessDecision(False, "free", reasons.get(status, f"unknown status {status!r}"))
