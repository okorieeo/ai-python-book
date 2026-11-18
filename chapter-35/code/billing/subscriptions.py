"""The life of a subscription. Every status change goes through here, nowhere else."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from django.db import transaction
from django.utils import timezone

from .models import Plan, Price, Provider, Subscription
from .pricing import Proration, add_months, interval_months, prorate

S = Subscription.Status

# From each status, where it may go next. Anything else is a bug, so we refuse it.
ALLOWED_TRANSITIONS = {
    S.TRIALING: {S.ACTIVE, S.PAST_DUE, S.CANCELED, S.EXPIRED},
    S.ACTIVE: {S.PAST_DUE, S.CANCELED, S.EXPIRED},
    S.PAST_DUE: {S.ACTIVE, S.CANCELED, S.EXPIRED},
    S.CANCELED: set(),
    S.EXPIRED: set(),
}


class InvalidTransition(Exception):
    pass


class AlreadySubscribed(Exception):
    pass


def transition(
    sub: Subscription, new_status: str, *, now: Optional[datetime] = None
) -> Subscription:
    if new_status not in ALLOWED_TRANSITIONS[S(sub.status)]:
        raise InvalidTransition(f"{sub.status} -> {new_status} is not allowed")
    sub.status = new_status
    if new_status == S.CANCELED:
        sub.canceled_at = now or timezone.now()
    sub.save()
    return sub


def start_subscription(
    user,
    price: Price,
    *,
    provider: str = Provider.MANUAL,
    provider_subscription_id: str = "",
    trial_days: int = 0,
    now: Optional[datetime] = None,
) -> Subscription:
    """Create a user's subscription. The database allows only one live subscription per user.

    billing_anchor is when the first PAID period starts: now, or the end of the trial. Every later
    period is counted from the anchor, so a subscription started on 31 January bills on the last
    day of each month instead of drifting to the 28th. period_number counts paid periods started
    (0 while the trial runs).
    """
    now = now or timezone.now()
    if Subscription.objects.filter(
        user=user, status__in=Subscription.LIVE_STATUSES
    ).exists():
        raise AlreadySubscribed(
            "This user already has a live subscription. Change it instead."
        )
    months = interval_months(price.interval)
    trial_end = now + timedelta(days=trial_days) if trial_days else None
    with transaction.atomic():
        return Subscription.objects.create(
            user=user,
            plan=price.plan,
            price=price,
            status=S.TRIALING if trial_days else S.ACTIVE,
            billing_anchor=trial_end or now,
            period_number=0 if trial_days else 1,
            current_period_start=now,
            current_period_end=trial_end or add_months(now, months),
            trial_end=trial_end,
            provider=provider,
            provider_subscription_id=provider_subscription_id,
        )


def renew(sub: Subscription, *, now: Optional[datetime] = None) -> Subscription:
    """A payment succeeded: move to the next period. Applies a scheduled downgrade, and ends a
    subscription the customer asked to cancel at the end of the period."""
    if sub.cancel_at_period_end:
        return transition(sub, S.CANCELED, now=now)
    if sub.pending_plan_id:
        sub.plan, sub.price = sub.pending_plan, sub.pending_price
        sub.pending_plan = sub.pending_price = None
    months = interval_months(sub.price.interval)
    sub.period_number += 1
    sub.current_period_start = add_months(
        sub.billing_anchor, months * (sub.period_number - 1)
    )
    sub.current_period_end = add_months(sub.billing_anchor, months * sub.period_number)
    if sub.status in (S.TRIALING, S.PAST_DUE):
        sub.status = S.ACTIVE
    sub.save()
    return sub


def mark_past_due(sub: Subscription) -> Subscription:
    return transition(sub, S.PAST_DUE)


def expire(sub: Subscription) -> Subscription:
    return transition(sub, S.EXPIRED)


def cancel(
    sub: Subscription, *, at_period_end: bool = True, now: Optional[datetime] = None
) -> Subscription:
    """Cancel now, or (the friendlier default) let the customer keep what they paid for."""
    if at_period_end:
        sub.cancel_at_period_end = True
        sub.save(update_fields=["cancel_at_period_end", "updated_at"])
        return sub
    return transition(sub, S.CANCELED, now=now)


def undo_cancel(sub: Subscription) -> Subscription:
    sub.cancel_at_period_end = False
    sub.save(update_fields=["cancel_at_period_end", "updated_at"])
    return sub


@dataclass(frozen=True)
class PlanChange:
    direction: str  # "upgrade", "downgrade" or "same"
    effective: str  # "now" or "next_renewal"
    proration: Optional[Proration]


def preview_plan_change(
    sub: Subscription, new_price: Price, *, now: Optional[datetime] = None
) -> PlanChange:
    """Upgrades start now, and the customer pays the difference for the time left. Downgrades
    wait for the next renewal, with no refund: the customer already paid for this period.
    """
    now = now or timezone.now()
    if (new_price.currency, new_price.interval) != (
        sub.price.currency,
        sub.price.interval,
    ):
        raise ValueError(
            "Changing currency or interval is a new subscription, not a plan change."
        )
    if new_price.plan.tier == sub.plan.tier:
        return PlanChange("same", "now", None)
    if new_price.plan.tier > sub.plan.tier:
        p = prorate(
            sub.price.amount_minor,
            new_price.amount_minor,
            sub.current_period_start,
            sub.current_period_end,
            now,
        )
        return PlanChange("upgrade", "now", p)
    return PlanChange("downgrade", "next_renewal", None)


def apply_plan_change(
    sub: Subscription, new_price: Price, *, now: Optional[datetime] = None
) -> PlanChange:
    change = preview_plan_change(sub, new_price, now=now)
    with transaction.atomic():
        if change.direction == "upgrade":
            sub.plan, sub.price = new_price.plan, new_price
            sub.pending_plan = sub.pending_price = None
        elif change.direction == "downgrade":
            sub.pending_plan, sub.pending_price = new_price.plan, new_price
        sub.save()
    return change
