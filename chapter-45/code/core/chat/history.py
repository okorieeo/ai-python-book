"""Fit a conversation into the model's context window: keep the newest turns, never lose the last user message."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


class ContextTooLong(Exception):
    pass


@dataclass(frozen=True)
class Message:
    role: str      # "user" | "assistant"
    content: str


def estimate_tokens(text: str) -> int:
    """A rough rule of thumb (about 4 characters per token). Use your provider's counter when you can."""
    return max(1, len(text) // 4)


def trim_history(messages: list[Message], *, max_tokens: int, system_tokens: int = 0, reserve_reply: int = 0,
                 estimate: Callable[[str], int] = estimate_tokens) -> tuple[list[Message], int]:
    """Return (kept messages, number dropped). The last message must be the user's new one and is always kept."""
    if not messages or messages[-1].role != "user":
        raise ValueError("the last message must be the user's")
    budget = max_tokens - system_tokens - reserve_reply
    last_cost = estimate(messages[-1].content)
    if last_cost > budget:
        raise ContextTooLong(f"the new message needs {last_cost} tokens but only {max(budget, 0)} are available")
    kept = [messages[-1]]
    used = last_cost
    for message in reversed(messages[:-1]):
        cost = estimate(message.content)
        if used + cost > budget:
            break
        kept.append(message)
        used += cost
    kept.reverse()
    while len(kept) > 1 and kept[0].role != "user":      # a conversation must not open with the assistant
        kept.pop(0)
    return kept, len(messages) - len(kept)
