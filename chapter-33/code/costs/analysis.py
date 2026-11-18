"""Questions about money that the ledger can answer. Pure functions over plain numbers."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

from ai.dto import Usage
from ai.pricing import ModelPrice, cost_micro_usd

from evals.stats import percentile


@dataclass(frozen=True)
class CacheReport:
    hit_rate: float
    actual_micro_usd: int
    without_caching_micro_usd: int

    @property
    def saved_micro_usd(self) -> int:
        return self.without_caching_micro_usd - self.actual_micro_usd


def cache_report(usages: Sequence[Usage], price: ModelPrice) -> CacheReport:
    """What caching saved: the bill you got against the bill if every input token had been fresh."""
    actual = sum(cost_micro_usd(u, price) for u in usages)
    fresh = sum(cost_micro_usd(Usage(input_tokens=u.total_input, output_tokens=u.output_tokens), price) for u in usages)
    total_in = sum(u.total_input for u in usages)
    read = sum(u.cache_read_tokens for u in usages)
    return CacheReport(read / total_in if total_in else 0.0, actual, fresh)


def forecast_month(daily_micro_usd: Sequence[int], horizon_days: int = 30) -> tuple[int, int]:
    """(expected, pessimistic) spend: the recent average, and the worst recent day, each times the horizon."""
    recent = list(daily_micro_usd)[-7:]
    if not recent:
        return (0, 0)
    return (round(sum(recent) / len(recent) * horizon_days), max(recent) * horizon_days)


def recommend_max_tokens(output_tokens: Sequence[int], *, headroom: float = 1.25, floor: int = 64,
                         ceiling: int = 4096, round_to: int = 64) -> dict:
    """
    A max_tokens that fits real replies without cutting many off. Uses the 99th percentile plus headroom.
    Also says how many of today's replies would be truncated, so lowering the cap is a decision with a number.
    """
    if not output_tokens:
        raise ValueError("need at least one sample")
    p99 = percentile(output_tokens, 99)
    value = min(ceiling, max(floor, math.ceil(p99 * headroom / round_to) * round_to))
    cut = sum(t > value for t in output_tokens) / len(output_tokens)
    return {"max_tokens": value, "p99": p99, "would_truncate": cut}


def spend_concentration(per_user_micro_usd: Sequence[int], top_share: float = 0.01) -> dict:
    """How much of the bill comes from the top 1% of users. Large values mean per-user limits matter more."""
    values = sorted((v for v in per_user_micro_usd if v >= 0), reverse=True)
    total = sum(values)
    if not values or total == 0:
        return {"users": len(values), "top_users": 0, "share": 0.0}
    k = max(1, math.ceil(len(values) * top_share))
    return {"users": len(values), "top_users": k, "share": sum(values[:k]) / total}
