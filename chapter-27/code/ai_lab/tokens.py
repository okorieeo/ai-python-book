"""Token estimates and exact counts."""
from __future__ import annotations

import math
from typing import Any, Sequence

from .catalog import ModelInfo

# Claude 4.7 and later use a tokenizer that produces about 30% more tokens than
# older ones. English text averages about 4 characters per token on the old
# tokenizer, so about 3 characters per token on the new one. This is only a
# rule of thumb. Other languages and code vary a lot.
DEFAULT_CHARS_PER_TOKEN = 3.0


def estimate_tokens(text: str, chars_per_token: float = DEFAULT_CHARS_PER_TOKEN) -> int:
    """A quick guess. Good enough to decide 'obviously fits' or 'obviously huge'.

    Never use it for billing. Use the usage the API returns for that.
    """
    if not text:
        return 0
    return math.ceil(len(text) / chars_per_token)


def count_tokens_anthropic(
    client: Any,
    *,
    model: str,
    messages: Sequence[dict],
    system: str | None = None,
) -> int:
    """Ask Anthropic to count tokens for a request without running it.

    The endpoint is free but rate limited, and the result is an estimate that
    can differ from the billed count by a small amount.
    """
    params: dict[str, Any] = {"model": model, "messages": list(messages)}
    if system:
        params["system"] = system
    return int(client.messages.count_tokens(**params).input_tokens)


def fits_in_context(model: ModelInfo, prompt_tokens: int, max_output: int) -> bool:
    """Input plus the largest reply you allow must fit in the context window."""
    return prompt_tokens + max_output <= model.context_window
