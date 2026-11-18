"""A model catalog: what each model can do and what it costs.

Prices are USD per million tokens (MTok). The Claude rows come from the Claude
Platform pricing and model pages and were checked on 2026-11-04. Prices and
model names change, so treat this file as data you maintain, not as truth.
Always confirm on the provider's own pricing page before you budget.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

AS_OF = "2026-11-04"


@dataclass(frozen=True)
class Price:
    """USD per million tokens."""

    input: float
    output: float
    cache_write_5m: float = 0.0
    cache_write_1h: float = 0.0
    cache_read: float = 0.0


@dataclass(frozen=True)
class ModelInfo:
    model_id: str
    provider: str  # "anthropic", "openai-compatible", "local"
    display_name: str
    tier: str  # "fast", "balanced", "strong", "frontier", "local"
    context_window: int  # tokens the model can read in one request
    max_output: int  # largest max_tokens the model accepts
    price: Price
    # Some models charge more per token once the prompt is long. Claude Haiku 5.5
    # is one: prompts over 100,000 tokens use the second price list.
    long_price: Optional[Price] = None
    long_threshold: Optional[int] = None
    notes: str = ""

    def price_for(self, prompt_tokens: int) -> Price:
        if self.long_price and self.long_threshold and prompt_tokens > self.long_threshold:
            return self.long_price
        return self.price


CATALOG: dict[str, ModelInfo] = {}


def register(model: ModelInfo) -> ModelInfo:
    """Add or replace a model. Use this for models you add yourself."""
    CATALOG[model.model_id] = model
    return model


def get_model(model_id: str) -> ModelInfo:
    try:
        return CATALOG[model_id]
    except KeyError:
        known = ", ".join(sorted(CATALOG)) or "(none)"
        raise KeyError(
            f"Unknown model {model_id!r}. Known models: {known}. "
            "Add it with ai_lab.catalog.register(...)."
        ) from None


def local_model(model_id: str, context_window: int = 32_768, max_output: int = 8_192) -> ModelInfo:
    """A model you run yourself (Ollama, vLLM). Tokens are free; hardware is not."""
    return ModelInfo(
        model_id=model_id,
        provider="local",
        display_name=f"{model_id} (local)",
        tier="local",
        context_window=context_window,
        max_output=max_output,
        price=Price(input=0.0, output=0.0),
        notes="No per-token fee. You pay for the machine and its electricity.",
    )


# ---- Claude, from platform.claude.com (models overview and pricing pages) ----
register(
    ModelInfo(
        model_id="claude-fable-5-1",
        provider="anthropic",
        display_name="Claude Fable 5.1",
        tier="frontier",
        context_window=1_000_000,
        max_output=128_000,
        price=Price(10.0, 50.0, cache_write_5m=12.5, cache_write_1h=20.0, cache_read=0.25),
        notes="Demanding reasoning and long-horizon agentic work. Slowest, most expensive.",
    )
)
register(
    ModelInfo(
        model_id="claude-opus-5-5",
        provider="anthropic",
        display_name="Claude Opus 5.5",
        tier="strong",
        context_window=1_000_000,
        max_output=128_000,
        price=Price(4.0, 20.0, cache_write_5m=5.0, cache_write_1h=8.0, cache_read=0.20),
        notes="Long-running agentic coding and knowledge work.",
    )
)
register(
    ModelInfo(
        model_id="claude-sonnet-5-5",
        provider="anthropic",
        display_name="Claude Sonnet 5.5",
        tier="balanced",
        context_window=1_000_000,
        max_output=128_000,
        price=Price(2.0, 10.0, cache_write_5m=2.5, cache_write_1h=4.0, cache_read=0.10),
        notes="Best combination of speed and intelligence. A sensible default for chat.",
    )
)
register(
    ModelInfo(
        model_id="claude-haiku-5-5",
        provider="anthropic",
        display_name="Claude Haiku 5.5",
        tier="fast",
        context_window=1_000_000,
        max_output=128_000,
        price=Price(0.10, 0.50, cache_write_5m=0.125, cache_write_1h=0.20, cache_read=0.01),
        long_price=Price(0.50, 2.50, cache_write_5m=0.625, cache_write_1h=1.0, cache_read=0.05),
        long_threshold=100_000,
        notes="Classification, extraction, routing. Prompts over 100K tokens cost more.",
    )
)
