"""Who can do what right now. The single place that answers: what does this user's plan include?"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Optional

from django.conf import settings
from django.utils import timezone

from .models import EntitlementOverride, Plan, PlanEntitlement, Subscription
from .registry import FEATURE, REGISTRY, get_def


@dataclass(frozen=True)
class Entitlement:
    key: str
    kind: str
    enabled: bool  # for a limit: always True; use `limit` to see how much
    limit: Optional[int]  # None = unlimited (limits only)
    source: str  # "plan:pro", "override", "default"

    def allows_amount(self, amount: int) -> bool:
        return self.kind == "limit" and (self.limit is None or amount <= self.limit)


def free_plan() -> Plan:
    return Plan.objects.get(code=settings.BILLING_FREE_PLAN_CODE)


def live_subscription(user) -> Optional[Subscription]:
    return (
        Subscription.objects.select_related("plan", "price")
        .filter(user=user, status__in=Subscription.LIVE_STATUSES)
        .first()
    )


def effective_plan(user, now=None) -> tuple[Plan, Optional[Subscription]]:
    """The plan that applies at `now`. Paid access ends when the provider says it does,
    plus a short grace window so a late webhook or a retried card never locks a paying user out.
    """
    now = now or timezone.now()
    sub = live_subscription(user)
    if sub is not None:
        if sub.status in (Subscription.Status.TRIALING, Subscription.Status.ACTIVE):
            if now < sub.current_period_end + timedelta(
                days=settings.BILLING_RENEWAL_GRACE_DAYS
            ):
                return sub.plan, sub
        elif sub.status == Subscription.Status.PAST_DUE:
            if now <= sub.current_period_end + timedelta(
                days=settings.BILLING_PAST_DUE_GRACE_DAYS
            ):
                return sub.plan, sub
    return free_plan(), None


def get_entitlements(user, now=None) -> dict[str, Entitlement]:
    """Every registered entitlement for this user: the plan's, then manual overrides on top."""
    now = now or timezone.now()
    plan, _ = effective_plan(user, now)
    rows = {e.key: e for e in PlanEntitlement.objects.filter(plan=plan)}
    result: dict[str, Entitlement] = {}
    for key, definition in REGISTRY.items():
        row = rows.get(key)
        if definition.kind == FEATURE:
            result[key] = Entitlement(
                key,
                FEATURE,
                bool(row and row.enabled),
                None,
                f"plan:{plan.code}" if row else "default",
            )
        else:  # a missing limit row means "none included", not "unlimited"
            result[key] = Entitlement(
                key,
                "limit",
                True,
                row.limit if row else 0,
                f"plan:{plan.code}" if row else "default",
            )
    # The newest unexpired override for each key wins.
    overrides = EntitlementOverride.objects.filter(user=user).order_by("created_at", "id")
    for o in overrides:
        if o.expires_at is not None and o.expires_at <= now:
            continue
        definition = get_def(o.key)
        if definition.kind == FEATURE:
            result[o.key] = Entitlement(o.key, FEATURE, o.enabled, None, "override")
        else:
            result[o.key] = Entitlement(
                o.key, "limit", True, o.limit if o.enabled else 0, "override"
            )
    return result


def has_feature(user, key: str, now=None) -> bool:
    ent = get_entitlements(user, now)[get_def(key).key]
    return ent.kind == FEATURE and ent.enabled


def limit_for(user, key: str, now=None) -> Optional[int]:
    """The numeric limit for `key`, or None if unlimited."""
    return get_entitlements(user, now)[get_def(key).key].limit
