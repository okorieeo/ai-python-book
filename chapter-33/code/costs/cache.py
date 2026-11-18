"""
A response cache for questions whose answer does not depend on who asks.

DANGER: a cached answer is shown to whoever asks the same question next. If the reply could contain anything
about one person (their name, their history, their documents) it must NEVER be shared. That is why caching is
opt-in per request via `scope`, and why a personal request has no scope and is never cached.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from typing import AsyncIterator, Callable, Protocol

from ai.dto import LLMRequest, ModelEvent, StreamEnd, TextDelta, Usage
from ai.resilience import LLMClient

CHUNK = 40


class Backend(Protocol):
    def get(self, key: str) -> str | None: ...
    def set(self, key: str, value: str, ttl: float) -> None: ...


class MemoryBackend:
    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self._data: dict[str, tuple[float, str]] = {}
        self._clock = clock

    def get(self, key: str) -> str | None:
        item = self._data.get(key)
        if item is None or item[0] <= self._clock():
            self._data.pop(key, None)
            return None
        return item[1]

    def set(self, key: str, value: str, ttl: float) -> None:
        self._data[key] = (self._clock() + ttl, value)


def cache_key(request: LLMRequest, *, prompt_version: str, scope: str) -> str:
    """Everything that can change the answer is in the key, so a prompt edit can never serve a stale reply."""
    payload = json.dumps([scope, prompt_version, request.model, request.system, request.max_tokens,
                          [[m.role, m.content] for m in request.messages]], ensure_ascii=False)
    return "resp:" + hashlib.sha256(payload.encode()).hexdigest()


@dataclass
class CachedClient:
    """Wraps any LLMClient. Only requests carrying a scope are eligible; only clean answers are stored."""
    inner: LLMClient
    backend: Backend
    prompt_version: str
    ttl: float = 3600.0
    scope_of: Callable[[LLMRequest], str | None] = lambda request: None
    hits: int = 0
    misses: int = 0

    async def stream(self, request: LLMRequest) -> AsyncIterator[ModelEvent]:
        scope = self.scope_of(request)
        if scope is None:                       # personal or unclassified: never cached
            async for event in self.inner.stream(request):
                yield event
            return
        key = cache_key(request, prompt_version=self.prompt_version, scope=scope)
        stored = self.backend.get(key)
        if stored is not None:
            self.hits += 1
            text = json.loads(stored)["text"]
            for i in range(0, len(text), CHUNK):
                yield TextDelta(text[i:i + CHUNK])
            yield StreamEnd("end_turn", Usage(), request.model, "cache:hit")      # a hit costs nothing
            return
        self.misses += 1
        parts: list[str] = []
        async for event in self.inner.stream(request):
            if isinstance(event, TextDelta):
                parts.append(event.text)
            elif isinstance(event, StreamEnd) and event.stop_reason == "end_turn" and parts:
                self.backend.set(key, json.dumps({"text": "".join(parts)}), self.ttl)
            yield event
