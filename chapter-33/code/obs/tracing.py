"""
Timing for AI turns, added WITHOUT touching ChatService: wrap its event stream.

The wrapper passes every event through unchanged and, when the stream ends (normally, with an error, or
because the client left), emits one TurnTrace: how long until the first word, how long in total, how it ended.
No content. Chapter 29's ledger records what a turn COST; this records how it FELT.
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from typing import AsyncIterator, Callable

from ai.dto import ServiceEvent, TextDelta, TurnFailed, TurnFinished, TurnStarted


@dataclass(frozen=True)
class TurnTrace:
    user_id: int
    conversation_id: int
    assistant_message_id: int | None
    outcome: str                 # complete | truncated | refused | failed | interrupted | cancelled | abandoned
    error_code: str
    first_token_ms: float | None
    total_ms: float
    chunks: int
    output_chars: int
    prompt_version: str
    model_hint: str

    def as_log(self) -> dict:
        return asdict(self)


async def traced(stream: AsyncIterator[ServiceEvent], *, user_id: int, conversation_id: int, prompt_version: str,
                 emit: Callable[[TurnTrace], None], model_hint: str = "",
                 clock: Callable[[], float] = time.monotonic) -> AsyncIterator[ServiceEvent]:
    started = clock()
    first: float | None = None
    chunks = chars = 0
    message_id: int | None = None
    outcome, code = "abandoned", ""
    try:
        async for event in stream:
            if isinstance(event, TurnStarted):
                message_id = event.assistant_message_id
            elif isinstance(event, TextDelta):
                chunks += 1
                chars += len(event.text)
                if first is None:
                    first = (clock() - started) * 1000
            elif isinstance(event, TurnFinished):
                outcome = event.status
            elif isinstance(event, TurnFailed):
                outcome, code = ("interrupted" if event.partial else "failed"), event.code
            yield event
    except BaseException:
        if outcome == "abandoned":
            outcome = "cancelled"      # the consumer went away, or an exception ended the stream
        raise
    finally:
        emit(TurnTrace(user_id, conversation_id, message_id, outcome, code, first, (clock() - started) * 1000,
                       chunks, chars, prompt_version, model_hint))
