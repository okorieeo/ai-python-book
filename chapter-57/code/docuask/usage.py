"""Database version of docuask_core.limits: one conditional UPDATE decides, so two simultaneous requests cannot both pass."""
from datetime import datetime, timezone

from django.db.models import F
from django.db.models.functions import Greatest

from docuask_core.limits import LimitExceeded, MONTHLY_METRICS, next_reset, period_start

from .models import UsageCounter


def consume(owner, plan, metric: str, amount: int = 1, now: datetime = None) -> None:
    now = now or datetime.now(timezone.utc)
    limit = getattr(plan, MONTHLY_METRICS[metric])
    start = period_start(now).date()
    counter, _ = UsageCounter.objects.get_or_create(owner=owner, metric=metric, period_start=start)
    # The WHERE clause is the check, the SET is the consume: both happen inside one statement.
    updated = UsageCounter.objects.filter(pk=counter.pk, used__lte=limit - amount).update(used=F("used") + amount)
    if not updated:
        counter.refresh_from_db()
        raise LimitExceeded(metric, limit, counter.used, next_reset(now))


def refund(owner, metric: str, amount: int, now: datetime = None) -> None:
    start = period_start(now or datetime.now(timezone.utc)).date()
    UsageCounter.objects.filter(owner=owner, metric=metric, period_start=start).update(used=Greatest(F("used") - amount, 0))


def snapshot(owner, plan, now: datetime = None) -> dict:
    now = now or datetime.now(timezone.utc)
    start = period_start(now).date()
    used = dict(UsageCounter.objects.filter(owner=owner, period_start=start).values_list("metric", "used"))
    return {"plan": plan.name, "resets_at": next_reset(now).isoformat(),
            "questions": {"used": used.get("questions", 0), "limit": plan.questions_per_month},
            "pages": {"used": used.get("pages", 0), "limit": plan.pages_per_month}}
