"""
The chat service: the ONE place that turns "a person said something" into "the model answered".

Views, WebSocket consumers and Celery tasks all call stream_reply(). None of them import the
provider SDK, build prompts, count tokens or touch UsageRecord. The service depends on small
interfaces (ports) for storage and budget, so it is tested here with in-memory fakes.
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import aclosing
from dataclasses import dataclass, field
from typing import AsyncIterator, Awaitable, Callable, Protocol

from .context import estimate_tokens, normalize_alternation, plan_context
from .errors import AIError, AIInputError, AIStreamInterrupted
from .pricing import ModelPrice, cost_or_none
from .resilience import CircuitBreaker, ConcurrencyLimiter, LLMClient, stream_with_fallback
from .dto import (ChatMessage, LLMRequest, ServiceEvent, StreamEnd, TextDelta, TurnFailed, TurnFinished,
                    TurnStarted, Usage)

logger = logging.getLogger("ai.service")

TRUNCATED = {"max_tokens", "model_context_window_exceeded"}


class ConversationNotFound(Exception):
    """Missing OR not yours. The two are deliberately indistinguishable (Chapter 17)."""


@dataclass(frozen=True)
class History:
    messages: tuple[ChatMessage, ...]
    summary: str | None = None


@dataclass(frozen=True)
class Turn:
    user_message_id: int
    assistant_message_id: int


@dataclass(frozen=True)
class TurnResult:
    status: str                  # complete | truncated | refused | interrupted | cancelled | failed
    text: str
    stop_reason: str
    usage: Usage
    usage_estimated: bool
    model: str
    request_id: str | None
    cost_micro_usd: int | None   # None = unknown model price, NOT zero
    prompt_version: str
    error_code: str = ""


class ConversationStore(Protocol):
    async def get_history(self, *, user_id: int, conversation_id: int) -> History: ...
    async def begin_turn(self, *, user_id: int, conversation_id: int, user_text: str) -> Turn: ...
    async def finish_turn(self, *, user_id: int, conversation_id: int, turn: Turn, result: TurnResult) -> None: ...
    async def schedule_summary(self, *, user_id: int, conversation_id: int) -> None: ...


BudgetCheck = Callable[[int, int], Awaitable[None]]   # (user_id, estimated_tokens) -> raises AIBudgetExceeded


@dataclass
class AISettings:
    primary_model: str
    fallback_model: str | None
    system_prompt: str
    prompt_version: str
    max_output_tokens: int = 1024
    max_input_tokens: int = 60_000
    expected_output_tokens: int = 500
    first_token_timeout: float = 20.0
    max_user_chars: int = 8_000
    prices: dict[str, ModelPrice] | None = None


class ChatService:
    def __init__(self, *, client: LLMClient, store: ConversationStore, budget_check: BudgetCheck,
                 settings: AISettings, limiter: ConcurrencyLimiter | None = None,
                 breakers: dict[str, CircuitBreaker] | None = None):
        self.client = client
        self.store = store
        self.budget_check = budget_check
        self.cfg = settings
        self.limiter = limiter or ConcurrencyLimiter(50)
        self.breakers = breakers if breakers is not None else {}

    # ------------------------------------------------------------------------------
    async def stream_reply(self, *, user_id: int, conversation_id: int, text: str) -> AsyncIterator[ServiceEvent]:
        cfg = self.cfg
        text = (text or "").strip()
        if not text or len(text) > cfg.max_user_chars:
            raise AIInputError("empty or oversized message")

        # 1. Ownership first. Services never trust the caller to have checked.
        history = await self.store.get_history(user_id=user_id, conversation_id=conversation_id)

        # 2. Plan what the model will see, then check the allowance BEFORE spending anything.
        messages = normalize_alternation([*history.messages, ChatMessage("user", text)])
        plan = plan_context(system=cfg.system_prompt, messages=messages, summary=history.summary,
                            max_input_tokens=cfg.max_input_tokens)
        await self.budget_check(user_id, plan.estimated_input + cfg.expected_output_tokens)

        # 3. Persist the question and an EMPTY answer marked "streaming", so a crash leaves a trace.
        turn = await self.store.begin_turn(user_id=user_id, conversation_id=conversation_id, user_text=text)
        if plan.needs_summary:
            await self.store.schedule_summary(user_id=user_id, conversation_id=conversation_id)
        yield TurnStarted(turn.user_message_id, turn.assistant_message_id)

        models = [m for m in (cfg.primary_model, cfg.fallback_model) if m]
        requests = [LLMRequest(m, plan.system, plan.messages, cfg.max_output_tokens) for m in models]
        parts: list[str] = []
        current_model = cfg.primary_model
        end: StreamEnd | None = None
        failure: AIError | None = None
        internal_error = False

        def attempt(model: str) -> None:
            nonlocal current_model
            current_model = model

        def result(status: str, *, stop_reason: str = "", usage: Usage | None = None, estimated: bool = False,
                   request_id: str | None = None, error_code: str = "") -> TurnResult:
            used = usage or Usage()
            return TurnResult(status=status, text="".join(parts), stop_reason=stop_reason, usage=used,
                              usage_estimated=estimated, model=current_model, request_id=request_id,
                              cost_micro_usd=cost_or_none(used, current_model, cfg.prices),
                              prompt_version=cfg.prompt_version, error_code=error_code)

        def estimate_usage() -> Usage:
            return Usage(input_tokens=plan.estimated_input, output_tokens=estimate_tokens("".join(parts)) if parts else 0)

        try:
            async with self.limiter.slot():
                stream = stream_with_fallback(client=self.client, requests=requests, breakers=self.breakers,
                                              first_event_timeout=cfg.first_token_timeout, on_attempt=attempt)
                async with aclosing(stream):          # always close the provider stream, even on cancel
                    async for event in stream:
                        if isinstance(event, TextDelta):
                            parts.append(event.text)
                            yield event
                        elif isinstance(event, StreamEnd):
                            end = event
        except AIStreamInterrupted as exc:
            failure = exc.cause
            await self._save(user_id, conversation_id, turn,
                             result("interrupted", usage=estimate_usage(), estimated=True,
                                    request_id=exc.request_id, error_code=exc.cause.code))
            yield TurnFailed(turn.assistant_message_id, exc.cause.code, exc.cause.user_message, exc.retry_after, partial=True)
            return
        except AIError as exc:
            failure = exc
            await self._save(user_id, conversation_id, turn,
                             result("failed", request_id=exc.request_id, error_code=exc.code))
            yield TurnFailed(turn.assistant_message_id, exc.code, exc.user_message, exc.retry_after, partial=bool(parts))
            return
        except (asyncio.CancelledError, GeneratorExit):
            # The person closed the app or the connection dropped. Keep what they saw, and what it cost.
            await asyncio.shield(self._save(user_id, conversation_id, turn,
                                            result("cancelled", usage=estimate_usage(), estimated=True)))
            raise
        except Exception:
            logger.exception("unexpected error in chat turn", extra={"conversation_id": conversation_id})
            internal_error = True
        if internal_error or end is None:
            await self._save(user_id, conversation_id, turn, result("failed", error_code="internal"))
            yield TurnFailed(turn.assistant_message_id, "internal", "Something went wrong on our side.", None, partial=bool(parts))
            return

        status = "truncated" if end.stop_reason in TRUNCATED else "refused" if end.stop_reason == "refusal" else "complete"
        current_model = end.model
        await self._save(user_id, conversation_id, turn,
                         result(status, stop_reason=end.stop_reason, usage=end.usage, request_id=end.request_id))
        yield TurnFinished(turn.assistant_message_id, status, end.stop_reason)

    async def _save(self, user_id: int, conversation_id: int, turn: Turn, result: TurnResult) -> None:
        await self.store.finish_turn(user_id=user_id, conversation_id=conversation_id, turn=turn, result=result)
        logger.info("ai_turn", extra={"conversation_id": conversation_id, "status": result.status, "model": result.model,
                                      "input_tokens": result.usage.total_input, "output_tokens": result.usage.output_tokens,
                                      "cost_micro_usd": result.cost_micro_usd, "request_id": result.request_id,
                                      "prompt_version": result.prompt_version})
