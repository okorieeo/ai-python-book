"""Pick a model for a job: the cheapest one that meets your requirements.

This is the idea behind model routing. Real routers also look at the content of
the request; this one only looks at what the job needs, which is a good start.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from .catalog import CATALOG, ModelInfo, Price

TIER_ORDER = {"local": 0, "fast": 1, "balanced": 2, "strong": 3, "frontier": 4}


@dataclass(frozen=True)
class Job:
    name: str
    min_tier: str = "fast"
    prompt_tokens: int = 1_000
    max_output: int = 500
    providers: Optional[tuple[str, ...]] = None  # e.g. ("anthropic",) to stay with one vendor


class NoModelFits(LookupError):
    pass


def blended_price(price: Price, input_share: float = 0.8) -> float:
    """One number to compare models by: a weighted average of input and output price."""
    return price.input * input_share + price.output * (1 - input_share)


def choose_model(job: Job, models: Optional[Iterable[ModelInfo]] = None) -> ModelInfo:
    candidates = []
    for model in models if models is not None else CATALOG.values():
        if TIER_ORDER[model.tier] < TIER_ORDER[job.min_tier]:
            continue
        if job.providers and model.provider not in job.providers:
            continue
        if job.prompt_tokens + job.max_output > model.context_window:
            continue
        if job.max_output > model.max_output:
            continue
        candidates.append(model)
    if not candidates:
        raise NoModelFits(
            f"No model satisfies job {job.name!r}. "
            "Relax a requirement or register more models."
        )

    def sort_key(model: ModelInfo):
        price = blended_price(model.price_for(job.prompt_tokens))
        return (price, TIER_ORDER[model.tier])

    return min(candidates, key=sort_key)
