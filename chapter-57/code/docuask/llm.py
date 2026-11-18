"""Calls to the models. NOT executed in the book's test environment (no API key or network).

Models (strings from Anthropic's model list at the time of writing; check the current list before you deploy):
  ANSWER_MODEL = "claude-sonnet-5-5"   writes the answer from the search results
  FAST_MODEL   = "claude-haiku-5-5"    rewrites follow-up questions (cheap and quick)
"""
from typing import AsyncIterator, List, Tuple

import anthropic
from django.conf import settings

from docuask_core.citations import ParsedAnswer, StreamAssembler, parse_response
from docuask_core.prompting import REWRITE_PROMPT, SYSTEM_PROMPT, RetrievedChunk, build_messages, rewrite_messages

ANSWER_MODEL = getattr(settings, "ANSWER_MODEL", "claude-sonnet-5-5")
FAST_MODEL = getattr(settings, "FAST_MODEL", "claude-haiku-5-5")
MAX_ANSWER_TOKENS = 1024

_client = anthropic.Anthropic(timeout=60.0, max_retries=2)          # reads ANTHROPIC_API_KEY from the environment
_aclient = anthropic.AsyncAnthropic(timeout=60.0, max_retries=2)


def rewrite_question(history: List[dict], question: str) -> str:
    """"And what about carry-over?" cannot be searched on its own. Make it self-contained first."""
    if not history:
        return question
    resp = _client.messages.create(model=FAST_MODEL, max_tokens=200, system=REWRITE_PROMPT,
                                   messages=rewrite_messages(history, question))
    text = "".join(b.text for b in resp.content if b.type == "text").strip()
    return text if 0 < len(text) < 500 else question


def answer(question: str, chunks: List[RetrievedChunk], history: List[dict]) -> Tuple[ParsedAnswer, int, int]:
    resp = _client.messages.create(model=ANSWER_MODEL, max_tokens=MAX_ANSWER_TOKENS, system=SYSTEM_PROMPT,
                                   messages=build_messages(question, chunks, history))
    parsed = parse_response([b.model_dump() for b in resp.content], chunks)
    return parsed, resp.usage.input_tokens, resp.usage.output_tokens


async def stream_answer(question: str, chunks: List[RetrievedChunk], history: List[dict]) -> AsyncIterator[dict]:
    """Yields {"type": "token", "text": ...} while the answer is written, then one {"type": "done", ...}.
    Raw events are used (stream=True) so citations_delta events arrive exactly as the API documents them."""
    assembler = StreamAssembler()
    stream = await _aclient.messages.create(model=ANSWER_MODEL, max_tokens=MAX_ANSWER_TOKENS, system=SYSTEM_PROMPT,
                                            messages=build_messages(question, chunks, history), stream=True)
    async for event in stream:
        text = assembler.feed(event.model_dump())
        if text:
            yield {"type": "token", "text": text}
    parsed = parse_response(assembler.content(), chunks)
    yield {"type": "done", "parsed": parsed, "input_tokens": assembler.input_tokens, "output_tokens": assembler.output_tokens}
