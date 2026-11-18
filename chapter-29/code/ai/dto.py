"""Plain data the AI layer passes around. No Django, no provider SDK."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Union

Role = Literal["user", "assistant"]


@dataclass(frozen=True)
class ChatMessage:
    role: Role
    content: str


@dataclass(frozen=True)
class Usage:
    """Token counts for one model call. The four fields are billed at four different rates."""

    input_tokens: int = 0        # uncached input
    output_tokens: int = 0       # includes any thinking tokens
    cache_write_tokens: int = 0  # input written to the prompt cache
    cache_read_tokens: int = 0   # input served from the prompt cache

    @property
    def total_input(self) -> int:
        return self.input_tokens + self.cache_write_tokens + self.cache_read_tokens

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(
            self.input_tokens + other.input_tokens,
            self.output_tokens + other.output_tokens,
            self.cache_write_tokens + other.cache_write_tokens,
            self.cache_read_tokens + other.cache_read_tokens,
        )


@dataclass(frozen=True)
class LLMRequest:
    model: str
    system: str
    messages: tuple[ChatMessage, ...]
    max_tokens: int


# ---- what a model client yields -------------------------------------------------
@dataclass(frozen=True)
class TextDelta:
    text: str


@dataclass(frozen=True)
class StreamEnd:
    stop_reason: str
    usage: Usage
    model: str
    request_id: str | None = None


ModelEvent = Union[TextDelta, StreamEnd]


# ---- what the chat service yields to the transport (SSE, WebSocket) --------------
@dataclass(frozen=True)
class TurnStarted:
    user_message_id: int
    assistant_message_id: int


@dataclass(frozen=True)
class TurnFinished:
    assistant_message_id: int
    status: str        # complete | truncated | refused
    stop_reason: str


@dataclass(frozen=True)
class TurnFailed:
    assistant_message_id: int
    code: str
    user_message: str
    retry_after: int | None
    partial: bool      # True when the person has already seen some text


ServiceEvent = Union[TurnStarted, TextDelta, TurnFinished, TurnFailed]
