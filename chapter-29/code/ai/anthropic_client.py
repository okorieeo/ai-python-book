"""
The ONLY file in the project that imports the Anthropic SDK. Everything else sees LLMRequest in,
ModelEvent out, and the errors in ai/errors.py.
"""
from __future__ import annotations

from typing import AsyncIterator

import anthropic
from anthropic import AsyncAnthropic

from .dto import LLMRequest, ModelEvent, StreamEnd, TextDelta, Usage
from .errors import AIConnectionFailed, AIServerError, AITimeout
from .provider_errors import error_for_status, parse_retry_after


class AnthropicLLM:
    def __init__(self, *, api_key: str, timeout: float = 60.0, max_retries: int = 1):
        # One layer of retries only. The SDK retries twice by default; stacked on our fallback and
        # the app's own retry button, three layers can turn one hiccup into a minute of waiting.
        self._client = AsyncAnthropic(api_key=api_key, timeout=timeout, max_retries=max_retries)

    async def stream(self, request: LLMRequest) -> AsyncIterator[ModelEvent]:
        try:
            async with self._client.messages.stream(
                model=request.model,
                max_tokens=request.max_tokens,
                # A block list lets us mark the system prompt cacheable. Caching only happens once the
                # prefix passes the model's minimum length; check usage.cache_* to see whether it did.
                system=[{"type": "text", "text": request.system, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": m.role, "content": m.content} for m in request.messages],
            ) as stream:
                async for text in stream.text_stream:
                    yield TextDelta(text)
                final = await stream.get_final_message()
        except anthropic.APITimeoutError as exc:            # subclass of APIConnectionError: catch it first
            raise AITimeout(str(exc)) from exc
        except anthropic.APIConnectionError as exc:
            raise AIConnectionFailed(str(exc)) from exc
        except anthropic.APIStatusError as exc:
            raise error_for_status(
                exc.status_code,
                retry_after=parse_retry_after(exc.response.headers.get("retry-after")),
                request_id=getattr(exc, "request_id", None),
            ) from exc
        except anthropic.APIError as exc:                   # e.g. an error event inside the stream
            raise AIServerError(str(exc)) from exc

        usage = final.usage
        yield StreamEnd(
            stop_reason=final.stop_reason or "end_turn",
            usage=Usage(
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cache_write_tokens=getattr(usage, "cache_creation_input_tokens", 0) or 0,
                cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
            ),
            model=final.model,
            request_id=getattr(final, "_request_id", None),
        )
