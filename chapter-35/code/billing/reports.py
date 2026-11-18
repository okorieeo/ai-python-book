"""Questions the business asks of the usage ledger."""

from __future__ import annotations

from datetime import datetime

from django.db.models import Count, Sum

from .models import UsageEvent


def cost_by_user(
    start: datetime, end: datetime, *, limit: int = 20, usage_key: str = "ai.message"
) -> list[dict]:
    """Who cost us the most between two moments? Costs are in micro-dollars (millionths of a dollar)."""
    rows = (
        UsageEvent.objects.filter(
            key=usage_key, occurred_at__gte=start, occurred_at__lt=end
        )
        .values("user_id")
        .annotate(
            cost_micro_usd=Sum("cost_micro_usd"),
            messages=Sum("quantity"),
            events=Count("id"),
        )
        .order_by("-cost_micro_usd")[:limit]
    )
    return list(rows)
