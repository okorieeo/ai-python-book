"""The one file that knows about the Anthropic SDK. Everything else talks to the
ModelClient protocol."""
import anthropic
from django.conf import settings

from core.security.env import require_secret

from .agent import ModelTurn, ModelUnavailable, Usage


class AnthropicClient:
    def __init__(self, *, model: str | None = None, max_tokens: int = 1500, timeout: float = 30.0):
        self.model = model or settings.ASSISTANT_MODEL
        self.max_tokens = max_tokens
        # The SDK retries 429 and 5xx answers with backoff; two retries is plenty for an
        # interactive request.
        self._client = anthropic.Anthropic(api_key=require_secret("ANTHROPIC_API_KEY"), timeout=timeout, max_retries=2)

    def complete(self, *, system, messages, tools, on_text=None) -> ModelTurn:
        try:
            with self._client.messages.stream(
                model=self.model, max_tokens=self.max_tokens, system=system, messages=messages, tools=tools,
            ) as stream:
                if on_text:
                    for chunk in stream.text_stream:
                        on_text(chunk)
                final = stream.get_final_message()
        # connection errors, rate limits, 5xx once retries are used up
        except anthropic.APIError as exc:
            raise ModelUnavailable(type(exc).__name__) from exc

        content = []
        for block in final.content:
            if block.type == "text":
                content.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                content.append({"type": "tool_use", "id": block.id, "name": block.name, "input": block.input})
        return ModelTurn(
            content=content,
            stop_reason=final.stop_reason or "end_turn",
            usage=Usage(final.usage.input_tokens, final.usage.output_tokens),
        )
