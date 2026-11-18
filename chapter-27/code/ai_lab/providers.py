"""One small interface over different model APIs.

The goal is a seam, not a framework. Your product code builds a ChatRequest and
gets a Completion back, and only this file knows how Anthropic, OpenAI or a
local server want the request shaped. Keep the interface small: the more
provider features you hide behind it, the more you lose.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Iterator, Optional, Protocol

from .cost import TokenUsage

VALID_ROLES = ("user", "assistant")


@dataclass(frozen=True)
class Message:
    role: str  # "user" or "assistant". The system prompt is a separate field.
    content: str

    def __post_init__(self) -> None:
        if self.role not in VALID_ROLES:
            raise ValueError(
                f"role must be one of {VALID_ROLES}, got {self.role!r}. "
                "Put the system prompt in ChatRequest.system instead."
            )


@dataclass(frozen=True)
class ChatRequest:
    model: str
    messages: tuple[Message, ...]
    system: Optional[str] = None
    max_tokens: int = 1024
    # Claude's "effort" dial: "low", "medium" or "high" (some models accept more
    # levels; see the effort page in the docs). None = the model's default.
    effort: Optional[str] = None
    # Provider-specific extras. Use sparingly: each one ties you to one provider.
    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.messages:
            raise ValueError("A request needs at least one message.")
        if self.max_tokens < 1:
            raise ValueError("max_tokens must be at least 1.")


@dataclass(frozen=True)
class Completion:
    text: str
    model: str
    provider: str
    stop_reason: str
    usage: TokenUsage
    latency_ms: int

    @property
    def was_cut_off(self) -> bool:
        """True when the reply stopped because it hit max_tokens."""
        return self.stop_reason in ("max_tokens", "length")


@dataclass(frozen=True)
class Chunk:
    """One streamed piece. The last chunk has text="" and the final completion."""

    text: str = ""
    completion: Optional[Completion] = None


class LLMProvider(Protocol):
    name: str

    def complete(self, request: ChatRequest) -> Completion: ...

    def stream(self, request: ChatRequest) -> Iterator[Chunk]: ...


def _now_ms() -> float:
    return time.perf_counter() * 1000


# --------------------------------------------------------------------------
# Anthropic (Claude Messages API)
# --------------------------------------------------------------------------
class AnthropicProvider:
    name = "anthropic"

    def __init__(
        self,
        client: Any = None,
        *,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = 60.0,
        max_retries: int = 2,
    ) -> None:
        if client is None:
            import anthropic  # imported here so tests and other providers do not need a key

            kwargs: dict[str, Any] = {"timeout": timeout, "max_retries": max_retries}
            if api_key:
                kwargs["api_key"] = api_key
            if base_url:
                kwargs["base_url"] = base_url
            client = anthropic.Anthropic(**kwargs)
        self.client = client

    def _params(self, request: ChatRequest) -> dict[str, Any]:
        params: dict[str, Any] = {
            "model": request.model,
            "max_tokens": request.max_tokens,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
        }
        if request.system:
            params["system"] = request.system
        if request.effort:
            params["output_config"] = {"effort": request.effort}
        # Do NOT pass temperature, top_p or top_k to the current Claude 5.x models.
        # Sonnet 5.5 rejects them with a 400, and the Haiku 5.5 page says to omit them.
        params.update(request.extra)
        return params

    @staticmethod
    def _text(message: Any) -> str:
        # Replies are a list of blocks. With thinking on there can be "thinking"
        # blocks before the "text" block, so join only the text ones.
        return "".join(b.text for b in message.content if getattr(b, "type", "") == "text")

    def complete(self, request: ChatRequest) -> Completion:
        started = _now_ms()
        message = self.client.messages.create(**self._params(request))
        return Completion(
            text=self._text(message),
            model=message.model,
            provider=self.name,
            stop_reason=str(message.stop_reason),
            usage=TokenUsage.from_anthropic(message.usage),
            latency_ms=int(_now_ms() - started),
        )

    def stream(self, request: ChatRequest) -> Iterator[Chunk]:
        started = _now_ms()
        with self.client.messages.stream(**self._params(request)) as stream:
            for piece in stream.text_stream:
                yield Chunk(text=piece)
            final = stream.get_final_message()
        yield Chunk(
            completion=Completion(
                text=self._text(final),
                model=final.model,
                provider=self.name,
                stop_reason=str(final.stop_reason),
                usage=TokenUsage.from_anthropic(final.usage),
                latency_ms=int(_now_ms() - started),
            )
        )


# --------------------------------------------------------------------------
# OpenAI and anything that speaks the same HTTP shape (Ollama, vLLM, gateways)
# --------------------------------------------------------------------------
class OpenAICompatProvider:
    """Uses the Chat Completions shape, which almost every server understands.

    OpenAI's current guidance for new projects is its Responses API, so a
    product built only on OpenAI would likely use that. We use Chat Completions
    here because OpenAI, Ollama, vLLM and most gateways all accept it, which
    lets one class talk to all of them for plain text in, text out.
    """

    def __init__(
        self,
        client: Any = None,
        *,
        name: str = "openai-compatible",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = 60.0,
        max_retries: int = 2,
        token_param: str = "max_completion_tokens",
    ) -> None:
        self.name = name
        # OpenAI's newer models want max_completion_tokens. Many local servers
        # still expect the older max_tokens. Pick the one your server accepts.
        self.token_param = token_param
        if client is None:
            import openai

            kwargs: dict[str, Any] = {"timeout": timeout, "max_retries": max_retries}
            # Local servers ignore the key but the SDK insists on one being set.
            kwargs["api_key"] = api_key or "not-needed-locally"
            if base_url:
                kwargs["base_url"] = base_url
            client = openai.OpenAI(**kwargs)
        self.client = client

    def _params(self, request: ChatRequest) -> dict[str, Any]:
        messages: list[dict[str, str]] = []
        if request.system:
            messages.append({"role": "system", "content": request.system})
        messages.extend({"role": m.role, "content": m.content} for m in request.messages)
        params: dict[str, Any] = {
            "model": request.model,
            "messages": messages,
            self.token_param: request.max_tokens,
        }
        if request.effort:
            params["reasoning_effort"] = request.effort
        params.update(request.extra)
        return params

    def complete(self, request: ChatRequest) -> Completion:
        started = _now_ms()
        response = self.client.chat.completions.create(**self._params(request))
        choice = response.choices[0]
        return Completion(
            text=choice.message.content or "",
            model=response.model,
            provider=self.name,
            stop_reason=str(choice.finish_reason),
            usage=TokenUsage.from_openai(response.usage),
            latency_ms=int(_now_ms() - started),
        )

    def stream(self, request: ChatRequest) -> Iterator[Chunk]:
        started = _now_ms()
        params = self._params(request)
        params["stream"] = True
        params["stream_options"] = {"include_usage": True}
        parts: list[str] = []
        finish = "unknown"
        usage = None
        model = request.model
        for event in self.client.chat.completions.create(**params):
            model = getattr(event, "model", model) or model
            if getattr(event, "usage", None):
                usage = event.usage
            if not event.choices:
                continue
            choice = event.choices[0]
            delta = choice.delta.content if choice.delta else None
            if delta:
                parts.append(delta)
                yield Chunk(text=delta)
            if choice.finish_reason:
                finish = str(choice.finish_reason)
        yield Chunk(
            completion=Completion(
                text="".join(parts),
                model=model,
                provider=self.name,
                stop_reason=finish,
                usage=TokenUsage.from_openai(usage),
                latency_ms=int(_now_ms() - started),
            )
        )
