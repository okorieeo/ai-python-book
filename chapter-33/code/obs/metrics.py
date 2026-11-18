"""Health numbers for a window of recent AI turns. Input rows come from the ledger plus the traces."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from evals.stats import percentile

ERROR_STATUSES = {"failed", "interrupted"}


@dataclass
class WindowMetrics:
    n: int = 0
    error_rate: float = 0.0
    interrupted_rate: float = 0.0
    refusal_rate: float = 0.0
    truncation_rate: float = 0.0
    p50_first_token_ms: float = 0.0
    p95_first_token_ms: float = 0.0
    p95_total_ms: float = 0.0
    cache_hit_rate: float | None = None      # None when no input tokens were recorded
    cost_micro_usd: int = 0
    unpriced_calls: int = 0
    thumbs_down_rate: float | None = None    # among rated turns; None when nobody rated


def summarize_window(rows: Iterable[Mapping]) -> WindowMetrics:
    """
    Each row: status, first_token_ms (or None), total_ms, input_tokens, cache_read_tokens, cache_write_tokens,
    cost_micro_usd (or None), rating (+1, -1 or None). Missing keys are treated as absent, not as zero cost.
    """
    rows = list(rows)
    n = len(rows)
    if n == 0:
        return WindowMetrics()
    status = lambda r: r.get("status", "")
    first = [r["first_token_ms"] for r in rows if r.get("first_token_ms") is not None]
    totals = [r["total_ms"] for r in rows if r.get("total_ms") is not None]
    total_input = sum(r.get("input_tokens", 0) + r.get("cache_read_tokens", 0) + r.get("cache_write_tokens", 0) for r in rows)
    cache_read = sum(r.get("cache_read_tokens", 0) for r in rows)
    rated = [r["rating"] for r in rows if r.get("rating") in (1, -1)]
    return WindowMetrics(
        n=n,
        error_rate=sum(status(r) in ERROR_STATUSES for r in rows) / n,
        interrupted_rate=sum(status(r) == "interrupted" for r in rows) / n,
        refusal_rate=sum(status(r) == "refused" for r in rows) / n,
        truncation_rate=sum(status(r) == "truncated" for r in rows) / n,
        p50_first_token_ms=percentile(first, 50),
        p95_first_token_ms=percentile(first, 95),
        p95_total_ms=percentile(totals, 95),
        cache_hit_rate=(cache_read / total_input) if total_input else None,
        cost_micro_usd=sum(r.get("cost_micro_usd") or 0 for r in rows),
        unpriced_calls=sum(r.get("cost_micro_usd", 0) is None for r in rows),
        thumbs_down_rate=(sum(x == -1 for x in rated) / len(rated)) if rated else None,
    )
