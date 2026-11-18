"""
Keeping chat alive when the provider is slow, overloaded or down.

Three small tools, each testable without a network:
  CircuitBreaker      stop hammering a model that keeps failing
  ConcurrencyLimiter  cap simultaneous streams so we do not trigger the provider's own 429s
  stream_with_fallback  try the primary model, then the fallback, but only while no text has been shown
"""
from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from typing import AsyncIterator, Callable, Protocol, Sequence

from .errors import AIBusy, AIError, AIStreamInterrupted, AIUnavailable
from .dto import LLMRequest, ModelEvent, TextDelta


class LLMClient(Protocol):
    def stream(self, request: LLMRequest) -> AsyncIterator[ModelEvent]: ...


class CircuitBreaker:
    """closed -> (N failures in a row) -> open -> (after reset_after seconds) -> one probe -> closed/open."""

    def __init__(self, *, failure_threshold: int = 5, reset_after: float = 30.0, clock: Callable[[], float] = time.monotonic):
        self.failure_threshold = failure_threshold
        self.reset_after = reset_after
        self._clock = clock
        self._failures = 0
        self._opened_at: float | None = None
        self._probing = False

    @property
    def state(self) -> str:
        if self._opened_at is None:
            return "closed"
        if self._clock() - self._opened_at >= self.reset_after:
            return "half_open"
        return "open"

    def allow(self) -> bool:
        state = self.state
        if state == "closed":
            return True
        if state == "half_open" and not self._probing:
            self._probing = True   # exactly one request tests the water
            return True
        return False

    def record_success(self) -> None:
        self._failures, self._opened_at, self._probing = 0, None, False

    def record_failure(self) -> None:
        self._failures += 1
        self._probing = False
        if self._failures >= self.failure_threshold or self._opened_at is not None:
            self._opened_at = self._clock()


class ConcurrencyLimiter:
    """At most `limit` streams at once; a caller waits up to `wait` seconds, then gets AIBusy."""

    def __init__(self, limit: int, wait: float = 2.0):
        self._sem = asyncio.Semaphore(limit)
        self._wait = wait

    @asynccontextmanager
    async def slot(self):
        try:
            await asyncio.wait_for(self._sem.acquire(), timeout=self._wait)
        except asyncio.TimeoutError:
            raise AIBusy("too many streams in flight", retry_after=5) from None
        try:
            yield
        finally:
            self._sem.release()


async def stream_with_fallback(
    *,
    client: LLMClient,
    requests: Sequence[LLMRequest],
    breakers: dict[str, CircuitBreaker],
    first_event_timeout: float,
    on_attempt: Callable[[str], None] | None = None,
) -> AsyncIterator[ModelEvent]:
    """
    Try each request (primary model first). Fall back to the next ONLY when:
      * the failure is one another model could avoid (overload, timeout, 5xx), and
      * no text has reached the person yet.
    Once text has been shown we cannot swap models invisibly, so we raise AIStreamInterrupted
    carrying what was already sent; the caller decides how to save and present it.
    """
    last_error: AIError | None = None
    for request in requests:
        breaker = breakers.setdefault(request.model, CircuitBreaker())
        if not breaker.allow():
            continue
        shown: list[str] = []
        if on_attempt is not None:
            on_attempt(request.model)      # lets the caller know which model is really streaming
        agen = client.stream(request).__aiter__()
        try:
            timeout = first_event_timeout
            while True:
                try:
                    event = await asyncio.wait_for(agen.__anext__(), timeout=timeout)
                except StopAsyncIteration:
                    break
                except asyncio.TimeoutError:
                    from .errors import AITimeout
                    raise AITimeout("no first token in time") from None
                timeout = None      # the deadline applies to the FIRST event only
                if isinstance(event, TextDelta):
                    shown.append(event.text)
                yield event
            breaker.record_success()
            return
        except AIError as exc:
            if exc.fallback_ok:
                breaker.record_failure()
            if shown:
                raise AIStreamInterrupted("".join(shown), exc) from exc
            if not exc.fallback_ok:
                raise
            last_error = exc
        finally:
            aclose = getattr(agen, "aclose", None)
            if aclose is not None:
                await aclose()
    raise AIUnavailable(str(last_error or "all models unavailable"),
                        retry_after=getattr(last_error, "retry_after", None),
                        request_id=getattr(last_error, "request_id", None))
