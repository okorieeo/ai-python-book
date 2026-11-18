"""Counting what users do, and stopping them at their limit.

Two moments matter. Before an expensive thing (a model call) you CHECK that the user has
room. After it, you RECORD what happened. Recording never refuses: the work is already done.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone as dt_timezone
from typing import Optional

from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone

from .entitlements import effective_plan, get_entitlements
from .models import BillingAccount, UsageEvent
from .registry import LIMIT, REGISTRY, EntitlementDef, get_def


class LimitExceeded(Exception):
    def __init__(self, key: str, limit: int, used: int, requested: int):
        self.key, self.limit, self.used, self.requested = key, limit, used, requested
        super().__init__(f"{key}: limit {limit}, used {used}, requested {requested}")


def _utc_month(now: datetime) -> tuple[datetime, datetime]:
    start = now.astimezone(dt_timezone.utc).replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )
    end = (
        start.replace(year=start.year + 1, month=1)
        if start.month == 12
        else start.replace(month=start.month + 1)
    )
    return start, end


def period_window(
    user, definition: EntitlementDef, now: datetime
) -> tuple[datetime, datetime]:
    """The time window a limit is counted in. Paid users count per billing period, so a
    plan that renews on the 14th resets on the 14th. Everyone else counts per UTC month.
    """
    if definition.period == "day":
        start = now.astimezone(dt_timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        return start, start + timedelta(days=1)
    _, sub = effective_plan(user, now)
    if sub is not None and sub.current_period_start <= now < sub.current_period_end:
        return sub.current_period_start, sub.current_period_end
    return _utc_month(now)


def limit_key_for_usage(usage_key: str) -> Optional[str]:
    for key, d in REGISTRY.items():
        if d.kind == LIMIT and d.usage_key == usage_key:
            return key
    return None


def used_in_window(user, usage_key: str, start: datetime, end: datetime) -> int:
    total = UsageEvent.objects.filter(
        user=user, key=usage_key, occurred_at__gte=start, occurred_at__lt=end
    ).aggregate(t=Sum("quantity"))["t"]
    return total or 0


def check_can_use(
    user, usage_key: str, quantity: int = 1, now: Optional[datetime] = None
) -> None:
    """Raise LimitExceeded if recording `quantity` more would pass the user's limit."""
    now = now or timezone.now()
    limit_key = limit_key_for_usage(usage_key)
    if limit_key is None:
        return
    ent = get_entitlements(user, now)[limit_key]
    if ent.limit is None:
        return
    start, end = period_window(user, get_def(limit_key), now)
    used = used_in_window(user, usage_key, start, end)
    if used + quantity > ent.limit:
        raise LimitExceeded(limit_key, ent.limit, used, quantity)


def check_stock_limit(
    user, key: str, current_count: int, adding: int = 1, now=None
) -> None:
    """For limits you count yourself, like saved conversations: pass in how many there are now."""
    ent = get_entitlements(user, now)[get_def(key).key]
    if ent.limit is not None and current_count + adding > ent.limit:
        raise LimitExceeded(key, ent.limit, current_count, adding)


def record_usage(
    user,
    usage_key: str,
    quantity: int,
    idempotency_key: str,
    *,
    cost_micro_usd: int = 0,
    meta: Optional[dict] = None,
    enforce: bool = False,
    now: Optional[datetime] = None,
) -> tuple[UsageEvent, bool]:
    """Write one usage event, once. Returns (event, created).

    Sending the same idempotency_key again changes nothing and returns the original event,
    so a retried task or a repeated webhook can never double-count.
    With enforce=True the limit is checked inside the same locked transaction (use it when the
    thing has not happened yet and recording is the reservation).
    """
    now = now or timezone.now()
    if quantity < 1:
        raise ValueError("quantity must be at least 1")
    with transaction.atomic():
        account, _ = BillingAccount.objects.get_or_create(user=user)
        BillingAccount.objects.select_for_update().get(
            pk=account.pk
        )  # serialize this user's writes
        existing = UsageEvent.objects.filter(idempotency_key=idempotency_key).first()
        if existing is not None:
            return existing, False
        if enforce:
            check_can_use(user, usage_key, quantity, now)
        try:
            with transaction.atomic():
                event = UsageEvent.objects.create(
                    user=user,
                    key=usage_key,
                    quantity=quantity,
                    occurred_at=now,
                    idempotency_key=idempotency_key,
                    cost_micro_usd=cost_micro_usd,
                    meta=meta or {},
                )
        except IntegrityError:  # lost a race with an identical request
            return UsageEvent.objects.get(idempotency_key=idempotency_key), False
        return event, True


def usage_summary(user, now: Optional[datetime] = None) -> dict:
    """What the account page shows: for each metered limit, the limit, use so far and what is left."""
    now = now or timezone.now()
    ents = get_entitlements(user, now)
    out = {}
    for key, d in REGISTRY.items():
        if d.kind != LIMIT or not d.usage_key:
            continue
        start, end = period_window(user, d, now)
        used = used_in_window(user, d.usage_key, start, end)
        limit = ents[key].limit
        out[key] = {
            "limit": limit,
            "used": used,
            "remaining": None if limit is None else max(0, limit - used),
            "period_start": start,
            "period_end": end,
        }
    return out
