import json
import unittest

from ai.dto import ChatMessage, LLMRequest, StreamEnd, TextDelta, Usage
from ai.pricing import DEFAULT_PRICES
from ai.testing import FakeLLM, Script

from .analysis import CacheReport, cache_report, forecast_month, recommend_max_tokens, spend_concentration
from .cache import CachedClient, MemoryBackend, cache_key
from .routing import RouteConfig, RouteFeatures, route

S, H = "claude-sonnet-5-5", "claude-haiku-5-5"


def req(text="What are your opening hours?", system="sys", model=S):
    return LLMRequest(model, system, (ChatMessage("user", text),), 200)


class FakeClock:
    def __init__(self): self.t = 0.0
    def __call__(self): return self.t


async def collect(client, request):
    return [e async for e in client.stream(request)]


def public(request):
    return "faq"


class CacheTests(unittest.IsolatedAsyncioTestCase):
    def make(self, scripts=None, clock=None, **kw):
        llm = FakeLLM({S: scripts or [Script(chunks=["We open ", "at 9."], usage=Usage(500, 20))]})
        backend = MemoryBackend(clock or FakeClock())
        return llm, CachedClient(llm, backend, "v1", ttl=100, scope_of=public, **kw)

    async def test_second_identical_request_is_served_from_cache_for_free(self):
        llm, client = self.make()
        first = await collect(client, req())
        second = await collect(client, req())
        self.assertEqual(len(llm.calls), 1)
        self.assertEqual((client.hits, client.misses), (1, 1))
        self.assertEqual("".join(e.text for e in second if isinstance(e, TextDelta)), "We open at 9.")
        end = second[-1]
        self.assertIsInstance(end, StreamEnd)
        self.assertEqual((end.usage, end.request_id), (Usage(), "cache:hit"))
        self.assertEqual(first[-1].usage, Usage(500, 20))

    async def test_requests_without_a_scope_are_never_cached(self):
        llm = FakeLLM({S: [Script()]})
        client = CachedClient(llm, MemoryBackend(FakeClock()), "v1")      # default scope_of returns None
        await collect(client, req()); await collect(client, req())
        self.assertEqual(len(llm.calls), 2)
        self.assertEqual((client.hits, client.misses), (0, 0))

    async def test_scope_separates_audiences(self):
        llm = FakeLLM({S: [Script(chunks=["a"])]})
        scopes = iter(["tenant-a", "tenant-b"])
        client = CachedClient(llm, MemoryBackend(FakeClock()), "v1", scope_of=lambda r: next(scopes))
        await collect(client, req()); await collect(client, req())
        self.assertEqual(len(llm.calls), 2)

    async def test_expiry(self):
        clock = FakeClock()
        llm, client = self.make(clock=clock)
        await collect(client, req())
        clock.t = 99
        await collect(client, req())
        self.assertEqual(len(llm.calls), 1)
        clock.t = 101
        await collect(client, req())
        self.assertEqual(len(llm.calls), 2)

    async def test_a_prompt_or_version_change_cannot_serve_a_stale_answer(self):
        llm, client = self.make(scripts=[Script(chunks=["old"]), Script(chunks=["new"])])
        await collect(client, req(system="prompt A"))
        out = await collect(client, req(system="prompt B"))
        self.assertEqual(out[0].text, "new")
        k1 = cache_key(req(), prompt_version="v1", scope="faq")
        self.assertNotEqual(k1, cache_key(req(), prompt_version="v2", scope="faq"))
        self.assertNotEqual(k1, cache_key(req(model=H), prompt_version="v1", scope="faq"))
        self.assertEqual(k1, cache_key(req(), prompt_version="v1", scope="faq"))

    async def test_truncated_and_empty_answers_are_not_stored(self):
        llm, client = self.make(scripts=[Script(chunks=["cut off"], stop_reason="max_tokens"), Script(chunks=["whole"])])
        await collect(client, req()); await collect(client, req())
        self.assertEqual(len(llm.calls), 2)
        out = await collect(client, req())              # the second (whole) answer WAS stored
        self.assertEqual(len(llm.calls), 2)
        self.assertEqual(out[0].text, "whole")

    async def test_failures_are_not_cached_and_still_propagate(self):
        from ai.errors import AIOverloaded
        llm, client = self.make(scripts=[Script(fail_before=AIOverloaded()), Script(chunks=["ok"])])
        with self.assertRaises(AIOverloaded):
            await collect(client, req())
        self.assertEqual((await collect(client, req()))[0].text, "ok")

    async def test_long_answers_replay_in_chunks(self):
        llm, client = self.make(scripts=[Script(chunks=["x" * 130])])
        await collect(client, req())
        replay = await collect(client, req())
        deltas = [e for e in replay if isinstance(e, TextDelta)]
        self.assertEqual(len(deltas), 4)
        self.assertEqual("".join(d.text for d in deltas), "x" * 130)


class RoutingTests(unittest.TestCase):
    cfg = RouteConfig(strong_model=S, cheap_model=H)

    def r(self, **kw):
        return route(RouteFeatures(**kw), self.cfg)

    def test_simple_tasks_go_cheap(self):
        self.assertEqual(self.r(tags=frozenset({"classification"})).model, H)
        self.assertEqual(self.r(tags=frozenset({"title", "summary"})).model, H)

    def test_unknown_or_missing_tags_default_to_strong(self):
        self.assertEqual(self.r().model, S)
        self.assertEqual(self.r(tags=frozenset({"brainstorm"})).model, S)

    def test_mixed_tags_are_strong_unless_every_tag_is_cheap(self):
        self.assertEqual(self.r(tags=frozenset({"summary", "brainstorm"})).model, S)

    def test_safety_beats_cost(self):
        self.assertEqual(self.r(tags=frozenset({"summary", "medical"})).reason, "sensitive topic")
        self.assertEqual(self.r(tags=frozenset({"smalltalk", "safety"})).model, S)

    def test_attachments_long_inputs_and_retries_go_strong(self):
        cheap = frozenset({"summary"})
        self.assertEqual(self.r(tags=cheap, has_attachment=True).model, S)
        self.assertEqual(self.r(tags=cheap, estimated_input_tokens=4001).model, S)
        self.assertEqual(self.r(tags=cheap, estimated_input_tokens=4000).model, H)
        self.assertEqual(self.r(tags=cheap, retry_after_bad_answer=True).reason, "person asked again after a bad answer")


class AnalysisTests(unittest.TestCase):
    SONNET = DEFAULT_PRICES[S]

    def test_cache_report_savings(self):
        us = [Usage(100, 50, 0, 9_900), Usage(100, 50, 0, 9_900)]
        rep = cache_report(us, self.SONNET)
        self.assertAlmostEqual(rep.hit_rate, 0.99)
        self.assertGreater(rep.saved_micro_usd, 0)
        self.assertEqual(rep.without_caching_micro_usd, 2 * (10_000 * 2 + 50 * 10))
        self.assertEqual(rep.actual_micro_usd, 2 * (200 + 500 + 990))
        self.assertEqual(rep.saved_micro_usd, 41_000 - 3_380)

    def test_cache_writes_can_make_caching_a_net_loss(self):
        one_shot = [Usage(0, 10, 10_000, 0)]                  # written, never read again
        rep = cache_report(one_shot, self.SONNET)
        self.assertLess(rep.saved_micro_usd, 0)

    def test_empty_usage_list(self):
        self.assertEqual(cache_report([], self.SONNET), CacheReport(0.0, 0, 0))
        self.assertEqual(cache_report([], self.SONNET).hit_rate, 0.0)

    def test_forecast_uses_the_last_week(self):
        expected, worst = forecast_month([9_999_999] * 20 + [100, 100, 100, 100, 100, 100, 400])
        self.assertEqual(expected, round((600 + 400) / 7 * 30))
        self.assertEqual(worst, 400 * 30)
        self.assertEqual(forecast_month([]), (0, 0))

    def test_recommend_max_tokens(self):
        samples = [100] * 95 + [300] * 4 + [900]
        out = recommend_max_tokens(samples)
        self.assertEqual(out["max_tokens"] % 64, 0)
        self.assertGreaterEqual(out["max_tokens"], out["p99"])
        self.assertLessEqual(out["would_truncate"], 0.01)
        self.assertEqual(recommend_max_tokens([5])["max_tokens"], 64)
        self.assertEqual(recommend_max_tokens([10_000] * 10)["max_tokens"], 4096)
        with self.assertRaises(ValueError):
            recommend_max_tokens([])

    def test_spend_concentration(self):
        spend = [1_000_000] + [1_000] * 99
        out = spend_concentration(spend)
        self.assertEqual((out["users"], out["top_users"]), (100, 1))
        self.assertAlmostEqual(out["share"], 1_000_000 / (1_000_000 + 99_000))
        self.assertEqual(spend_concentration([])["share"], 0.0)


if __name__ == "__main__":
    unittest.main()
