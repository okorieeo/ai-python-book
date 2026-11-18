"""A scripted stand-in for the model, so streaming, fallback and cost logic can be tested offline."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import AsyncIterator, Sequence

from .errors import AIError
from .dto import LLMRequest, ModelEvent, StreamEnd, TextDelta, Usage


@dataclass
class Script:
    """What one call to the fake model does: wait, emit chunks, then end or raise."""
    chunks: Sequence[str] = ("Hello", " world")
    fail_before: AIError | None = None       # raise before the first chunk
    fail_after: AIError | None = None        # raise after all chunks, before StreamEnd
    delay_first: float = 0.0                 # seconds before the first chunk
    chunk_delay: float = 0.0
    stop_reason: str = "end_turn"
    usage: Usage = field(default_factory=lambda: Usage(input_tokens=100, output_tokens=10))
    request_id: str = "req_fake"


class FakeLLM:
    """scripts maps model name -> list of Scripts, consumed one per call (the last one repeats)."""

    def __init__(self, scripts: dict[str, list[Script]]):
        self.scripts = scripts
        self.calls: list[LLMRequest] = []

    async def stream(self, request: LLMRequest) -> AsyncIterator[ModelEvent]:
        self.calls.append(request)
        queue = self.scripts[request.model]
        script = queue.pop(0) if len(queue) > 1 else queue[0]
        if script.fail_before:
            raise script.fail_before
        if script.delay_first:
            await asyncio.sleep(script.delay_first)
        for i, chunk in enumerate(script.chunks):
            if i and script.chunk_delay:
                await asyncio.sleep(script.chunk_delay)
            yield TextDelta(chunk)
        if script.fail_after:
            raise script.fail_after
        yield StreamEnd(script.stop_reason, script.usage, request.model, script.request_id)

    def models_called(self) -> list[str]:
        return [r.model for r in self.calls]
