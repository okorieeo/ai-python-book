"""Turning a subscription record into a yes or no: does this user get the paid features now?"""
from dataclasses import dataclass
from typing import Optional

DAY = 86400


@dataclass(frozen=True)
class AccessDecision:
    paid: bool                 # True: give the paid features
    tier: str                  # "free", "pro" or "team"
    reason: str                # a short sentence for logs and for the billing page
    until: Optional[int] = None  # unix seconds when this decision stops being true, if known


FREE = AccessDecision(False, "free", "no subscription")


def decide_access(record, now: float, grace_days: int = 3) -> AccessDecision:
    """Decide from Stripe's subscription status. Unknown statuses get no access, never free access.

    active, trialing    paid
    past_due            paid for a short grace period after the first failed payment, then not
    active + cancel at period end   paid until the period ends
    canceled, unpaid, incomplete, incomplete_expired, paused, anything else   not paid
    """
    if record is None:
        return FREE
    status, tier = record.status, record.tier or "free"
    if status in {"active", "trialing"}:
        ended = record.cancel_at is not None and now >= record.cancel_at
        if ended:
            return AccessDecision(False, "free", "the subscription has ended", record.cancel_at)
        if status == "trialing":
            return AccessDecision(True, tier, "free trial", record.trial_end or record.period_end)
        if record.cancel_at_period_end:
            return AccessDecision(True, tier, "cancels at the end of the period", record.period_end)
        return AccessDecision(True, tier, "active", record.period_end)
    if status == "past_due":
        since = record.past_due_since if record.past_due_since is not None else now
        grace_end = since + grace_days * DAY
        if now < grace_end:
            return AccessDecision(True, tier, "payment failed, in the grace period", int(grace_end))
        return AccessDecision(False, "free", "payment failed and the grace period is over", int(grace_end))
    reasons = {
        "canceled": "the subscription was canceled",
        "unpaid": "the invoice stayed unpaid",
        "incomplete": "the first payment is not complete",
        "incomplete_expired": "the first payment was never completed",
        "paused": "the subscription is paused",
    }
    return AccessDecision(False, "free", reasons.get(status, f"unknown status {status!r}"))
