import asyncio
import json
import unittest

from ai.dto import TextDelta, TurnFailed, TurnFinished, TurnStarted

from .logpolicy import ContentLogPolicy, prepare_content, should_log_content
from .scrub import luhn_ok, scrub_pii
from .tracing import traced


class ScrubTests(unittest.TestCase):
    def test_luhn(self):
        self.assertTrue(luhn_ok("4111111111111111"))
        self.assertTrue(luhn_ok("5500005555555559"))
        self.assertFalse(luhn_ok("4111111111111112"))
        self.assertFalse(luhn_ok("123"))
        self.assertFalse(luhn_ok("41111111111111a1"))

    def test_emails_and_cards(self):
        out = scrub_pii("Mail ada@example.com, card 4111 1111 1111 1111 thanks")
        self.assertEqual(out, "Mail [EMAIL], card [CARD] thanks")
        self.assertEqual(scrub_pii("card 4111-1111-1111-1111"), "card [CARD]")

    def test_ordinary_long_numbers_survive(self):
        for keep in ["order 1234567890123", "tracking 9400111899223197428490", "id 4111111111111112", "2026-11-05", "ts 1699999999"]:
            self.assertEqual(scrub_pii(keep), keep, keep)

    def test_phones(self):
        self.assertEqual(scrub_pii("call +234 803 123 4567 now"), "call [PHONE] now")
        self.assertEqual(scrub_pii("call 0803 123 4567 now"), "call [PHONE] now")
        self.assertEqual(scrub_pii("call +2348031234567 now"), "call [PHONE] now")

    def test_names_are_not_caught_and_we_say_so(self):
        self.assertEqual(scrub_pii("My name is Chiamaka Okafor"), "My name is Chiamaka Okafor")

    def test_idempotent_and_empty(self):
        once = scrub_pii("ada@example.com")
        self.assertEqual(scrub_pii(once), once)
        self.assertEqual(scrub_pii(""), "")


class PolicyTests(unittest.TestCase):
    def test_all_is_forbidden_in_production_only(self):
        with self.assertRaises(ValueError):
            ContentLogPolicy(mode="all", environment="production")
        self.assertEqual(ContentLogPolicy(mode="all", environment="development").mode, "all")
        with self.assertRaises(ValueError):
            ContentLogPolicy(mode="verbose")
        with self.assertRaises(ValueError):
            ContentLogPolicy(mode="sampled", sample_percent=150)

    def test_off_logs_nothing_even_for_errors(self):
        p = ContentLogPolicy(mode="off")
        self.assertFalse(should_log_content(p, status="failed", message_id=1))

    def test_errors_mode_keeps_only_bad_endings(self):
        p = ContentLogPolicy(mode="errors")
        for bad in ("failed", "interrupted", "refused", "truncated"):
            self.assertTrue(should_log_content(p, status=bad, message_id=1))
        self.assertFalse(should_log_content(p, status="complete", message_id=1))

    def test_sampled_is_deterministic_and_close_to_the_rate(self):
        p = ContentLogPolicy(mode="sampled", sample_percent=10)
        picks = [should_log_content(p, status="complete", message_id=i) for i in range(10_000)]
        self.assertAlmostEqual(sum(picks) / len(picks), 0.10, delta=0.02)
        self.assertEqual(picks, [should_log_content(p, status="complete", message_id=i) for i in range(10_000)])
        self.assertTrue(should_log_content(p, status="failed", message_id=7))     # bad endings always kept

    def test_prepare_scrubs_redacts_and_truncates(self):
        p = ContentLogPolicy(mode="errors", max_chars=40)
        out = prepare_content("key sk-SECRET123 and ada@example.com " + "x" * 100, p, redact=lambda t: t.replace("sk-SECRET123", "[REDACTED]"))
        self.assertIn("[REDACTED]", out)
        self.assertIn("[EMAIL]", out)
        self.assertNotIn("sk-SECRET123", out)
        self.assertIn("truncated", out)
        self.assertLessEqual(len(out.split("...")[0]), 40)


class FakeClock:
    def __init__(self): self.t = 0.0
    def __call__(self): return self.t


def stream_of(events, clock=None, step=0.0):
    async def gen():
        for ev in events:
            if clock is not None:
                clock.t += step
            yield ev
    return gen()


class TracingTests(unittest.IsolatedAsyncioTestCase):
    async def run_traced(self, events, clock=None, step=0.0):
        traces, seen = [], []
        async for ev in traced(stream_of(events, clock, step), user_id=1, conversation_id=2, prompt_version="v1",
                               emit=traces.append, clock=clock or FakeClock()):
            seen.append(ev)
        return traces, seen

    async def test_events_pass_through_unchanged_and_timing_is_measured(self):
        clock = FakeClock()
        events = [TurnStarted(1, 2), TextDelta("Hi"), TextDelta(" there"), TurnFinished(2, "complete", "end_turn")]
        traces, seen = await self.run_traced(events, clock, step=0.1)
        self.assertEqual(seen, events)
        t = traces[0]
        self.assertEqual((t.outcome, t.chunks, t.output_chars, t.assistant_message_id), ("complete", 2, 8, 2))
        self.assertAlmostEqual(t.first_token_ms, 200, places=3)     # TurnStarted then first delta: two steps
        self.assertAlmostEqual(t.total_ms, 400, places=3)

    async def test_failure_before_text_and_after_text(self):
        t1, _ = await self.run_traced([TurnStarted(1, 2), TurnFailed(2, "unavailable", "x", None, False)])
        t2, _ = await self.run_traced([TurnStarted(1, 2), TextDelta("a"), TurnFailed(2, "provider_overloaded", "x", 3, True)])
        self.assertEqual((t1[0].outcome, t1[0].error_code, t1[0].first_token_ms), ("failed", "unavailable", None))
        self.assertEqual((t2[0].outcome, t2[0].error_code), ("interrupted", "provider_overloaded"))

    async def test_a_consumer_that_leaves_still_produces_a_trace(self):
        traces = []
        gen = traced(stream_of([TurnStarted(1, 2), TextDelta("a"), TextDelta("b")]), user_id=1, conversation_id=2,
                     prompt_version="v1", emit=traces.append)
        await gen.__anext__(); await gen.__anext__()
        await gen.aclose()
        self.assertEqual(len(traces), 1)
        self.assertEqual(traces[0].outcome, "cancelled")
        self.assertEqual(traces[0].chunks, 1)

    async def test_errors_inside_the_stream_still_emit_and_propagate(self):
        async def broken():
            yield TurnStarted(1, 2)
            raise RuntimeError("boom")
        traces = []
        with self.assertRaises(RuntimeError):
            async for _ in traced(broken(), user_id=1, conversation_id=2, prompt_version="v1", emit=traces.append):
                pass
        self.assertEqual(traces[0].outcome, "cancelled")

    async def test_the_log_form_contains_no_content(self):
        traces, _ = await self.run_traced([TurnStarted(1, 2), TextDelta("SECRET REPLY"), TurnFinished(2, "complete", "end_turn")])
        dumped = json.dumps(traces[0].as_log())
        self.assertNotIn("SECRET", dumped)
        self.assertIn("output_chars", dumped)


if __name__ == "__main__":
    unittest.main()
