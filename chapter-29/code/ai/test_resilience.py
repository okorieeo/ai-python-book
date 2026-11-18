import asyncio
import unittest

from .errors import (AIBadRequest, AIBusy, AIOverloaded, AIStreamInterrupted, AIUnavailable)
from .resilience import CircuitBreaker, ConcurrencyLimiter, stream_with_fallback
from .testing import FakeLLM, Script
from .dto import ChatMessage, LLMRequest, StreamEnd, TextDelta

P, F = "claude-sonnet-5-5", "claude-haiku-5-5"


def req(model):
    return LLMRequest(model, "sys", (ChatMessage("user", "hi"),), 100)


async def collect(client, breakers=None, timeout=1.0):
    out = []
    async for ev in stream_with_fallback(client=client, requests=[req(P), req(F)],
                                         breakers=breakers if breakers is not None else {}, first_event_timeout=timeout):
        out.append(ev)
    return out


class FakeClock:
    def __init__(self): self.t = 0.0
    def __call__(self): return self.t


class BreakerTests(unittest.TestCase):
    def test_opens_after_threshold_and_half_opens_after_reset(self):
        clock = FakeClock()
        b = CircuitBreaker(failure_threshold=3, reset_after=30, clock=clock)
        for _ in range(2):
            b.record_failure()
        self.assertEqual(b.state, "closed")
        b.record_failure()
        self.assertEqual(b.state, "open")
        self.assertFalse(b.allow())
        clock.t = 31
        self.assertEqual(b.state, "half_open")

    def test_half_open_lets_exactly_one_probe_through(self):
        clock = FakeClock()
        b = CircuitBreaker(failure_threshold=1, reset_after=10, clock=clock)
        b.record_failure()
        clock.t = 11
        self.assertTrue(b.allow())
        self.assertFalse(b.allow())

    def test_probe_success_closes_and_probe_failure_reopens(self):
        clock = FakeClock()
        b = CircuitBreaker(failure_threshold=1, reset_after=10, clock=clock)
        b.record_failure(); clock.t = 11; b.allow(); b.record_success()
        self.assertEqual(b.state, "closed")
        b.record_failure(); clock.t = 22; b.allow(); b.record_failure()
        self.assertEqual(b.state, "open")

    def test_success_resets_the_failure_count(self):
        b = CircuitBreaker(failure_threshold=3)
        b.record_failure(); b.record_failure(); b.record_success(); b.record_failure(); b.record_failure()
        self.assertEqual(b.state, "closed")


class LimiterTests(unittest.IsolatedAsyncioTestCase):
    async def test_second_caller_gets_busy_when_full(self):
        lim = ConcurrencyLimiter(1, wait=0.02)
        async with lim.slot():
            with self.assertRaises(AIBusy):
                async with lim.slot():
                    pass

    async def test_slot_is_released_even_on_error(self):
        lim = ConcurrencyLimiter(1, wait=0.02)
        with self.assertRaises(RuntimeError):
            async with lim.slot():
                raise RuntimeError("boom")
        async with lim.slot():
            pass


class FallbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_primary_success_never_touches_fallback(self):
        llm = FakeLLM({P: [Script()], F: [Script()]})
        events = await collect(llm)
        self.assertEqual(llm.models_called(), [P])
        self.assertIsInstance(events[-1], StreamEnd)

    async def test_overload_before_first_token_falls_back(self):
        llm = FakeLLM({P: [Script(fail_before=AIOverloaded())], F: [Script(chunks=["ok"])]})
        events = await collect(llm)
        self.assertEqual(llm.models_called(), [P, F])
        self.assertEqual("".join(e.text for e in events if isinstance(e, TextDelta)), "ok")
        self.assertEqual(events[-1].model, F)

    async def test_slow_first_token_counts_as_a_timeout_and_falls_back(self):
        llm = FakeLLM({P: [Script(delay_first=0.3)], F: [Script(chunks=["fast"])]})
        events = await collect(llm, timeout=0.05)
        self.assertEqual(llm.models_called(), [P, F])
        self.assertEqual(events[0], TextDelta("fast"))

    async def test_failure_after_text_is_never_hidden_by_a_fallback(self):
        llm = FakeLLM({P: [Script(chunks=["Par", "tial"], fail_after=AIOverloaded())], F: [Script()]})
        got = []
        with self.assertRaises(AIStreamInterrupted) as ctx:
            async for ev in stream_with_fallback(client=llm, requests=[req(P), req(F)], breakers={}, first_event_timeout=1):
                got.append(ev)
        self.assertEqual(ctx.exception.partial, "Partial")
        self.assertEqual(llm.models_called(), [P])          # fallback NOT called
        self.assertEqual(len(got), 2)

    async def test_our_own_bad_request_is_not_retried_on_another_model(self):
        llm = FakeLLM({P: [Script(fail_before=AIBadRequest())], F: [Script()]})
        with self.assertRaises(AIBadRequest):
            await collect(llm)
        self.assertEqual(llm.models_called(), [P])

    async def test_all_models_failing_raises_unavailable(self):
        llm = FakeLLM({P: [Script(fail_before=AIOverloaded())], F: [Script(fail_before=AIOverloaded(retry_after=7))]})
        with self.assertRaises(AIUnavailable) as ctx:
            await collect(llm)
        self.assertEqual(llm.models_called(), [P, F])
        self.assertEqual(ctx.exception.retry_after, 7)     # the last error's hint is passed on

    async def test_on_attempt_reports_each_model_tried(self):
        tried = []
        llm = FakeLLM({P: [Script(fail_before=AIOverloaded())], F: [Script()]})
        async for _ in stream_with_fallback(client=llm, requests=[req(P), req(F)], breakers={},
                                            first_event_timeout=1, on_attempt=tried.append):
            pass
        self.assertEqual(tried, [P, F])

    async def test_open_breaker_skips_the_primary_without_calling_it(self):
        breakers = {P: CircuitBreaker(failure_threshold=1, reset_after=1000)}
        breakers[P].record_failure()
        llm = FakeLLM({P: [Script()], F: [Script(chunks=["fb"])]})
        await collect(llm, breakers)
        self.assertEqual(llm.models_called(), [F])

    async def test_failures_open_the_breaker_so_later_calls_skip_the_primary(self):
        breakers = {P: CircuitBreaker(failure_threshold=2, reset_after=1000)}
        llm = FakeLLM({P: [Script(fail_before=AIOverloaded())], F: [Script()]})
        await collect(llm, breakers); await collect(llm, breakers)
        before = llm.models_called().count(P)
        await collect(llm, breakers)
        self.assertEqual(llm.models_called().count(P), before)   # primary not tried a third time

    async def test_everything_open_is_unavailable(self):
        breakers = {m: CircuitBreaker(failure_threshold=1, reset_after=1000) for m in (P, F)}
        for b in breakers.values():
            b.record_failure()
        with self.assertRaises(AIUnavailable):
            await collect(FakeLLM({P: [Script()], F: [Script()]}), breakers)


if __name__ == "__main__":
    unittest.main()
