"""Run every few minutes from Celery Beat (Chapter 15): compute the window, apply the rules, tell someone."""
import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from ai.models import UsageRecord
from feedback.models import MessageFeedback

from .alerts import AlertState, default_rules, evaluate
from .metrics import summarize_window
from .models import TurnTraceRow

logger = logging.getLogger("ai.alerts")
STATE_KEY = "ai-alert-state"
WINDOW = timedelta(minutes=15)


def window_rows(since):
    """One row per turn in the window, combining trace, ledger and feedback."""
    traces = {t.assistant_message_id: t for t in TurnTraceRow.objects.filter(created_at__gte=since, assistant_message_id__isnull=False)}
    ledger = {u.message_id: u for u in UsageRecord.objects.filter(created_at__gte=since, message_id__in=list(traces))}
    ratings = dict(MessageFeedback.objects.filter(message_id__in=list(traces)).values_list("message_id", "rating"))
    rows = []
    for mid, t in traces.items():
        u = ledger.get(mid)
        rows.append({
            "status": t.outcome, "first_token_ms": t.first_token_ms, "total_ms": t.total_ms,
            "input_tokens": u.input_tokens if u else 0, "cache_read_tokens": u.cache_read_tokens if u else 0,
            "cache_write_tokens": u.cache_write_tokens if u else 0,
            "cost_micro_usd": u.cost_micro_usd if u else 0, "rating": ratings.get(mid),
        })
    return rows


@shared_task
def check_ai_health():
    rules = default_rules(hourly_budget_micro_usd=getattr(settings, "AI_HOURLY_BUDGET_MICRO_USD", None))
    metrics = summarize_window(window_rows(timezone.now() - WINDOW))
    # Beat tasks land on different workers, so the streak counters live in the shared cache, not in memory.
    saved = cache.get(STATE_KEY) or {}
    state = AlertState(streaks=saved.get("streaks", {}), firing=set(saved.get("firing", [])))
    fired, resolved = state.update(rules, evaluate(rules, metrics))
    cache.set(STATE_KEY, {"streaks": state.streaks, "firing": sorted(state.firing)}, timeout=3600)
    for breach in fired:
        logger.error("ALERT %s: %s is %.4g (threshold %s %s)", breach.rule.name, breach.rule.metric, breach.value,
                     breach.rule.op, breach.rule.threshold, extra={"severity": breach.rule.severity})
    for name in resolved:
        logger.warning("RESOLVED %s", name)
