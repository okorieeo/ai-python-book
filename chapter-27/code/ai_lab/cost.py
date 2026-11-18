"""Turn token counts into dollars.

Every provider reports usage a little differently. This module converts them
into one TokenUsage shape so the rest of your code can add them up.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .catalog import ModelInfo

MTOK = 1_000_000
BATCH_MULTIPLIER = 0.5  # Claude Batch API: 50% off input and output
US_ONLY_MULTIPLIER = 1.1  # Claude inference_geo="us": 10% premium


@dataclass(frozen=True)
class TokenUsage:
    """Tokens in four buckets that are billed at four different rates."""

    input_tokens: int = 0  # fresh input, not read from the cache
    output_tokens: int = 0  # everything the model wrote, including thinking
    cache_read_tokens: int = 0
    cache_write_5m_tokens: int = 0
    cache_write_1h_tokens: int = 0

    @property
    def prompt_tokens(self) -> int:
        """Every input token the model saw, cached or not."""
        return (
            self.input_tokens
            + self.cache_read_tokens
            + self.cache_write_5m_tokens
            + self.cache_write_1h_tokens
        )

    def __add__(self, other: "TokenUsage") -> "TokenUsage":
        return TokenUsage(
            self.input_tokens + other.input_tokens,
            self.output_tokens + other.output_tokens,
            self.cache_read_tokens + other.cache_read_tokens,
            self.cache_write_5m_tokens + other.cache_write_5m_tokens,
            self.cache_write_1h_tokens + other.cache_write_1h_tokens,
        )

    @classmethod
    def from_anthropic(cls, usage: Any) -> "TokenUsage":
        """Claude reports cache reads and writes separately from input_tokens."""
        if usage is None:
            return cls()
        write_5m = write_1h = 0
        detail = getattr(usage, "cache_creation", None)
        if detail is not None:
            write_5m = int(getattr(detail, "ephemeral_5m_input_tokens", 0) or 0)
            write_1h = int(getattr(detail, "ephemeral_1h_input_tokens", 0) or 0)
        total_written = int(getattr(usage, "cache_creation_input_tokens", 0) or 0)
        if total_written and not (write_5m or write_1h):
            write_5m = total_written  # no breakdown given: assume the default 5 minutes
        return cls(
            input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
            output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
            cache_read_tokens=int(getattr(usage, "cache_read_input_tokens", 0) or 0),
            cache_write_5m_tokens=write_5m,
            cache_write_1h_tokens=write_1h,
        )

    @classmethod
    def from_openai(cls, usage: Any) -> "TokenUsage":
        """OpenAI-style usage: cached tokens are a subset of prompt_tokens."""
        if usage is None:
            return cls()
        prompt = int(getattr(usage, "prompt_tokens", 0) or 0)
        details = getattr(usage, "prompt_tokens_details", None)
        cached = int(getattr(details, "cached_tokens", 0) or 0) if details else 0
        return cls(
            input_tokens=max(prompt - cached, 0),
            output_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
            cache_read_tokens=cached,
        )


def cost_usd(
    model: ModelInfo,
    usage: TokenUsage,
    *,
    batch: bool = False,
    us_only: bool = False,
) -> float:
    """Dollar cost of one request (or a sum of requests)."""
    price = model.price_for(usage.prompt_tokens)
    total = (
        usage.input_tokens * price.input
        + usage.output_tokens * price.output
        + usage.cache_read_tokens * price.cache_read
        + usage.cache_write_5m_tokens * price.cache_write_5m
        + usage.cache_write_1h_tokens * price.cache_write_1h
    ) / MTOK
    if batch:
        total *= BATCH_MULTIPLIER
    if us_only:
        total *= US_ONLY_MULTIPLIER
    return total


@dataclass
class CostLedger:
    """Adds up usage and dollars per model. Chapter 29 stores the same facts in the database.

    Cost is worked out PER REQUEST and then added up. Do not add up tokens first
    and price the total: some models (Claude Haiku 5.5) charge a higher rate when
    a single prompt is long, and a sum of many short requests would be priced wrongly.
    """

    usage: dict[str, TokenUsage] = field(default_factory=dict)
    cost: dict[str, float] = field(default_factory=dict)

    def add(self, model: ModelInfo, usage: TokenUsage, **flags) -> float:
        request_cost = cost_usd(model, usage, **flags)
        key = model.model_id
        self.usage[key] = self.usage.get(key, TokenUsage()) + usage
        self.cost[key] = self.cost.get(key, 0.0) + request_cost
        return request_cost

    @property
    def total_usd(self) -> float:
        return sum(self.cost.values())


def conversation_usage(
    turns: int,
    *,
    system_tokens: int,
    user_tokens: int,
    reply_tokens: int,
) -> list[TokenUsage]:
    """Usage per request for a chat where every turn resends the whole history.

    Turn 1 sends system + 1 user message. Turn 2 sends system + user1 + reply1
    + user2, and so on. This is why long chats get expensive faster than they
    get long.
    """
    out: list[TokenUsage] = []
    history = 0
    for _ in range(turns):
        prompt = system_tokens + history + user_tokens
        out.append(TokenUsage(input_tokens=prompt, output_tokens=reply_tokens))
        history += user_tokens + reply_tokens
    return out
