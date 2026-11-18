"""A tiny model interface, a scripted stand-in for tests and a Claude adapter.

Chapter 29 builds the real service layer (streaming, history, cost tracking). This is
just enough to run and test prompts.
"""
import os
from dataclasses import dataclass
from typing import Callable, Optional


@dataclass
class LLMResult:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    stop_reason: str = "end_turn"


class ScriptedLLM:
    """Stands in for a model in tests: free, instant and repeatable. It is NOT a real model.

    reply is either a list of strings (returned in order) or a function
    (system, messages) -> str. Every call is recorded in self.calls.
    """

    model = "scripted-stand-in"

    def __init__(self, reply):
        self._reply = reply
        self._index = 0
        self.calls = []

    def complete(self, *, system, messages, max_tokens=800, schema=None) -> LLMResult:
        self.calls.append({"system": system, "messages": list(messages), "schema": schema})
        if callable(self._reply):
            text = self._reply(system, messages)
        else:
            text = self._reply[min(self._index, len(self._reply) - 1)]
            self._index += 1
        words_in = len(system.split()) + sum(len(m["content"].split()) for m in messages)
        return LLMResult(text=text, input_tokens=words_in, output_tokens=len(text.split()))


# Keywords the Claude API accepts in a structured-output schema. We send only these and
# enforce the rest (lengths, item counts) ourselves with prompts.structured.validate.
_API_SCHEMA_KEYS = {"type", "properties", "required", "items", "enum", "description", "additionalProperties"}


def api_schema(schema):
    """Strip a schema down to the simple structural keywords we send to the API."""
    if isinstance(schema, dict):
        out = {}
        for key, value in schema.items():
            if key == "properties":
                out[key] = {name: api_schema(sub) for name, sub in value.items()}
            elif key in _API_SCHEMA_KEYS:
                out[key] = api_schema(value) if key == "items" else value
        return out
    return schema


class AnthropicLLM:
    """Calls Claude through the official SDK (pip install anthropic).

    The key comes from ANTHROPIC_API_KEY and the model from PROMPT_MODEL. We never pass
    temperature, top_p or top_k: the newest Claude models reject non-default values.
    """

    def __init__(self, model: Optional[str] = None):
        import anthropic  # imported here so the rest of the package needs no SDK

        self._client = anthropic.Anthropic()
        self.model = model or os.environ.get("PROMPT_MODEL", "claude-sonnet-5-5")

    def complete(self, *, system, messages, max_tokens=800, schema=None) -> LLMResult:
        kwargs = {}
        if schema is not None:
            kwargs["output_config"] = {"format": {"type": "json_schema", "schema": api_schema(schema)}}
        response = self._client.messages.create(
            model=self.model, max_tokens=max_tokens, system=system, messages=messages, **kwargs
        )
        # Pick blocks by type: thinking blocks may come before the text block.
        text = "".join(block.text for block in response.content if block.type == "text")
        return LLMResult(
            text=text,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            stop_reason=response.stop_reason or "",
        )
