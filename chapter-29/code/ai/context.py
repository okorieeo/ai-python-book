"""
Decide which part of a conversation to send to the model.

The model remembers nothing between calls: every turn re-sends the history. That makes the
cost of a conversation grow with the SQUARE of its length, so history has to be planned.
Pure functions, no Django, no provider.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Sequence

from .errors import AIContextTooLong
from .dto import ChatMessage

PER_MESSAGE_OVERHEAD = 4


def estimate_tokens(text: str) -> int:
    """
    A deliberately pessimistic guess (3 characters per token; English averages nearer 4).
    Good enough for budget pre-checks. Billing uses the provider's own usage numbers.
    """
    return math.ceil(len(text) / 3) + PER_MESSAGE_OVERHEAD


@dataclass(frozen=True)
class ContextPlan:
    system: str
    messages: tuple[ChatMessage, ...]
    dropped: int            # how many OLD messages were left out
    estimated_input: int    # system + messages, by the estimate above

    @property
    def needs_summary(self) -> bool:
        """True when old messages were dropped: time to refresh the rolling summary."""
        return self.dropped > 0


def normalize_alternation(messages: Sequence[ChatMessage]) -> list[ChatMessage]:
    """
    Make roles strictly alternate by merging neighbours with the same role. A turn that failed
    leaves a user message with no answer; without this the next call would send two user
    messages in a row, which providers may reject or treat unpredictably. Empty messages are dropped.
    """
    out: list[ChatMessage] = []
    for msg in messages:
        if not msg.content.strip():
            continue
        if out and out[-1].role == msg.role:
            out[-1] = ChatMessage(msg.role, f"{out[-1].content}\n\n{msg.content}")
        else:
            out.append(msg)
    return out


def build_system(system: str, summary: str | None) -> str:
    if not summary:
        return system
    return f"{system}\n\nSummary of the earlier part of this conversation:\n{summary}"


def plan_context(
    *,
    system: str,
    messages: Sequence[ChatMessage],
    summary: str | None = None,
    max_input_tokens: int,
    count: Callable[[str], int] = estimate_tokens,
) -> ContextPlan:
    """
    Keep the newest messages that fit. Rules:
      * the newest message (the one being answered) is always kept; if it alone does not fit,
        raise AIContextTooLong instead of silently cutting what the person just wrote;
      * the kept list must start with a user message (providers reject a leading assistant turn);
      * dropped messages are older ones, never a gap in the middle.
    """
    if not messages:
        raise ValueError("plan_context needs at least one message")
    full_system = build_system(system, summary)
    budget = max_input_tokens - count(full_system)

    kept: list[ChatMessage] = []
    used = 0
    for msg in reversed(messages):
        cost = count(msg.content)
        if used + cost > budget:
            break
        kept.append(msg)
        used += cost
    kept.reverse()

    if not kept or kept[-1] is not messages[-1]:
        raise AIContextTooLong(f"newest message needs {count(messages[-1].content)} tokens; budget is {budget}")

    while kept and kept[0].role != "user":   # never start on an assistant turn
        used -= count(kept[0].content)
        kept.pop(0)

    return ContextPlan(
        system=full_system,
        messages=tuple(kept),
        dropped=len(messages) - len(kept),
        estimated_input=count(full_system) + used,
    )


def cumulative_input_tokens(turns: int, tokens_per_message: int, system_tokens: int = 0) -> int:
    """
    Input tokens billed over a whole conversation when every turn re-sends the full history.
    Turn k sends k user messages and k-1 replies. Used in the chapter to show the quadratic growth.
    """
    total = 0
    for k in range(1, turns + 1):
        total += system_tokens + (2 * k - 1) * tokens_per_message
    return total
