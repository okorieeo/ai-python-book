"""Model providers behind one small interface (Chapter 29's service-layer pattern).

The rest of the app only knows `stream()` and `complete()`. Swapping Anthropic for another vendor,
or for the fake used in tests, touches this file and nothing else.
"""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol

from django.conf import settings


@dataclass(frozen=True)
class Delta:
    text: str


@dataclass(frozen=True)
class Done:
    input_tokens: int
    output_tokens: int


class ProviderError(Exception):
    """Anything that goes wrong talking to the model. `retryable` tells the UI whether to offer Retry."""

    def __init__(self, message: str, *, retryable: bool = True):
        super().__init__(message)
        self.retryable = retryable


class ChatProvider(Protocol):
    def stream(self, *, system: str, messages: list[dict], max_tokens: int) -> AsyncIterator[Delta | Done]: ...

    async def complete(self, *, system: str, messages: list[dict], max_tokens: int) -> str: ...


class FakeProvider:
    """Deterministic provider for tests, demos and CI. No network, no cost."""

    def __init__(self, *, reply: str | None = None, delay: float = 0.0, fail_after: int | None = None,
                 summary: str = "SUMMARY"):
        self.reply, self.delay, self.fail_after, self.summary = reply, delay, fail_after, summary
        self.calls: list[dict] = []  # tests inspect what the model was sent

    async def stream(self, *, system, messages, max_tokens):
        self.calls.append({"system": system, "messages": list(messages)})
        text = self.reply if self.reply is not None else (
            f"You said: {messages[-1]['content']} (I can see {len(messages)} messages.)")
        for i, word in enumerate(text.split(" ")):
            if self.fail_after is not None and i >= self.fail_after:
                raise ProviderError("The model is unavailable right now.")
            if self.delay:
                await asyncio.sleep(self.delay)
            yield Delta(word if i == 0 else " " + word)
        yield Done(input_tokens=sum(len(m["content"]) for m in messages) // 4 + 1,
                   output_tokens=len(text) // 4 + 1)

    async def complete(self, *, system, messages, max_tokens):
        self.calls.append({"system": system, "messages": list(messages), "kind": "complete"})
        return self.summary


class AnthropicProvider:
    """Streams from the Anthropic Messages API with the official SDK."""

    def __init__(self, *, api_key: str, model: str, summary_model: str, client=None):
        import anthropic

        self._anthropic = anthropic
        self._client = client or anthropic.AsyncAnthropic(api_key=api_key, max_retries=2, timeout=60.0)
        self.model, self.summary_model = model, summary_model

    async def stream(self, *, system, messages, max_tokens):
        try:
            async with self._client.messages.stream(
                model=self.model, max_tokens=max_tokens, system=system, messages=messages,
            ) as stream:
                async for text in stream.text_stream:
                    yield Delta(text)
                final = await stream.get_final_message()
            yield Done(final.usage.input_tokens, final.usage.output_tokens)
        except self._anthropic.RateLimitError as exc:
            raise ProviderError("The AI service is busy. Please try again in a moment.") from exc
        except self._anthropic.APIStatusError as exc:
            raise ProviderError("The AI service returned an error.", retryable=exc.status_code >= 500) from exc
        except self._anthropic.APIConnectionError as exc:
            raise ProviderError("Could not reach the AI service.") from exc

    async def complete(self, *, system, messages, max_tokens):
        try:
            response = await self._client.messages.create(
                model=self.summary_model, max_tokens=max_tokens, system=system, messages=messages)
        except self._anthropic.APIError as exc:
            raise ProviderError("Could not reach the AI service.") from exc
        return "".join(block.text for block in response.content if block.type == "text")


def get_provider() -> ChatProvider:
    if settings.AI_PROVIDER == "anthropic":
        return AnthropicProvider(api_key=settings.ANTHROPIC_API_KEY, model=settings.AI_CHAT_MODEL,
                                 summary_model=settings.AI_SUMMARY_MODEL)
    return FakeProvider()
