"""Streams an AI answer to a client, with cancel, timeout and cleanup. Plain asyncio: no Django, no Channels."""
import asyncio
import logging
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import aclosing
from dataclasses import dataclass
from typing import Any, Protocol

from .protocol import server_message

logger = logging.getLogger("chat.streaming")

class ProviderError(Exception):
    """The AI provider failed (timeout, overloaded, 5xx...)."""

class GenerationBusy(Exception):
    """This connection already has a generation running."""

@dataclass(frozen=True)
class Delta:
    text: str

@dataclass(frozen=True)
class Usage:
    input_tokens: int
    output_tokens: int

class StreamingProvider(Protocol):
    name: str

    def stream(self, messages: list[dict]) -> AsyncIterator[Delta | Usage]: ...

def estimate_tokens(text: str) -> int:
    """A rough guess (about 4 characters per token) used only when the provider reports nothing."""
    return max(1, len(text) // 4) if text else 0

SendFn = Callable[[dict], Awaitable[None]]
# save_reply(conversation, text, usage, status) -> message id string (or None if nothing was stored)
SaveFn = Callable[[Any, str, Usage, str], Awaitable[str | None]]

class GenerationManager:
    """Owns the AI generations of ONE WebSocket connection."""

    def __init__(self, provider: StreamingProvider, send: SendFn, save_reply: SaveFn, *,
                 timeout: float = 60.0, max_active: int = 1):
        self.provider = provider
        self.send = send
        self.save_reply = save_reply
        self.timeout = timeout
        self.max_active = max_active
        self._reserved: set[str] = set()
        self._tasks: dict[str, asyncio.Task] = {}

    # ---- public API -------------------------------------------------
    def reserve(self) -> str:
        """Claim a slot and get the generation id. Lets the caller announce the id BEFORE streaming starts."""
        if len(self._reserved) >= self.max_active:
            raise GenerationBusy("A generation is already running.")
        generation_id = "gen_" + uuid.uuid4().hex[:10]
        self._reserved.add(generation_id)
        return generation_id

    def release(self, generation_id: str) -> None:
        self._reserved.discard(generation_id)

    def run(self, generation_id: str, *, conversation: Any, messages: list[dict]) -> None:
        self._tasks[generation_id] = asyncio.create_task(
            self._run(generation_id, conversation, messages), name=generation_id)

    async def cancel(self, generation_id: str) -> bool:
        task = self._tasks.get(generation_id)
        if task is None or task.done():
            return False
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        return True

    async def cancel_all(self) -> None:
        for generation_id in list(self._tasks):
            await self.cancel(generation_id)

    @property
    def active(self) -> int:
        return len(self._reserved)

    # ---- the work ---------------------------------------------------
    async def _safe_send(self, message: dict) -> bool:
        try:
            await self.send(message)
            return True
        except Exception:                        # the client is gone: stop wasting tokens
            return False

    async def _run(self, generation_id: str, conversation: Any, messages: list[dict]) -> None:
        parts: list[str] = []
        usage: Usage | None = None
        status = "completed"
        failure: tuple[str, str] | None = None
        try:
            async with asyncio.timeout(self.timeout):
                async with aclosing(self.provider.stream(messages)) as stream:
                    async for event in stream:
                        if isinstance(event, Delta):
                            parts.append(event.text)
                            delivered = await self._safe_send(server_message(
                                "assistant.delta", {"generation_id": generation_id, "text": event.text}))
                            if not delivered:
                                status = "canceled"
                                break
                        elif isinstance(event, Usage):
                            usage = event
        except asyncio.CancelledError:
            status = "canceled"
        except TimeoutError:
            status, failure = "failed", ("generation_timeout", "The assistant took too long to answer.")
        except ProviderError:
            status, failure = "failed", ("upstream_unavailable", "The assistant is temporarily unavailable.")
        except Exception:
            logger.exception("Generation %s crashed", generation_id)
            status, failure = "failed", ("generation_failed", "Something went wrong while generating the answer.")

        text = "".join(parts)
        if usage is None:
            prompt_text = " ".join(m.get("content", "") for m in messages)
            usage = Usage(estimate_tokens(prompt_text), estimate_tokens(text))
        try:
            message_id = None
            if text:                                         # keep partial answers, bill what was used
                message_id = await self.save_reply(conversation, text, usage, status)
            if failure:
                await self._safe_send(server_message("assistant.error", {
                    "generation_id": generation_id, "code": failure[0], "message": failure[1],
                    "partial_message_id": message_id}))
            else:
                await self._safe_send(server_message("assistant.end", {
                    "generation_id": generation_id, "message_id": message_id, "status": status,
                    "usage": {"input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens}}))
        except Exception:
            logger.exception("Could not finish generation %s", generation_id)
        finally:
            self._reserved.discard(generation_id)
            self._tasks.pop(generation_id, None)
