"""Cost reporting straight from the ledger. Chapter 33 builds dashboards on top of the same table."""
from datetime import date, timedelta

from django.db.models import Count, Sum
from django.db.models.functions import TruncDate

from .models import UsageRecord
from .pricing import format_usd


def daily_cost(days: int = 7):
    """Rows of (day, model, calls, input_tokens, output_tokens, cost_usd_text)."""
    since = date.today() - timedelta(days=days)
    rows = (UsageRecord.objects.filter(created_at__date__gte=since)
            .annotate(day=TruncDate("created_at"))
            .values("day", "model")
            .annotate(calls=Count("id"), tin=Sum("input_tokens"), tout=Sum("output_tokens"), micro=Sum("cost_micro_usd"))
            .order_by("-day", "model"))
    return [(r["day"], r["model"], r["calls"], r["tin"] or 0, r["tout"] or 0, format_usd(r["micro"] or 0)) for r in rows]


def top_spenders(limit: int = 10, days: int = 1):
    since = date.today() - timedelta(days=days)
    return list(UsageRecord.objects.filter(created_at__date__gte=since, user__isnull=False)
                .values("user_id").annotate(micro=Sum("cost_micro_usd")).order_by("-micro")[:limit])


def unpriced_calls(days: int = 7) -> int:
    """Calls whose model had no price in the table. Should be 0; alert when it is not."""
    since = date.today() - timedelta(days=days)
    return UsageRecord.objects.filter(created_at__date__gte=since, cost_micro_usd__isnull=True).count()
