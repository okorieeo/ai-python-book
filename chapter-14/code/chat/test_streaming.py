import asyncio
import unittest

from .ai_fake import FakeProvider
from .streaming import Delta, GenerationBusy, GenerationManager, ProviderError, Usage

HISTORY = [{"role": "user", "content": "Explain Celery in one sentence"}]

class Harness:
    """Collects what the manager sends and saves, standing in for a WebSocket and the database."""

    def __init__(self, provider, **kwargs):
        self.sent: list[dict] = []
        self.saved: list[tuple] = []
        self.fail_sends = False
        self.manager = GenerationManager(provider, self.send, self.save_reply, **kwargs)

    async def send(self, message):
        if self.fail_sends:
            raise ConnectionError("client went away")
        self.sent.append(message)

    async def save_reply(self, conversation, text, usage, status):
        self.saved.append((conversation, text, usage, status))
        return f"msg_{len(self.saved)}"

    def types(self):
        return [m["type"] for m in self.sent]

    async def wait_idle(self):
        while self.manager.active:
            await asyncio.sleep(0.005)

    def start(self):
        gid = self.manager.reserve()
        self.manager.run(gid, conversation="conv-1", messages=HISTORY)
        return gid

class FlakyProvider:
    name = "flaky"

    async def stream(self, messages):
        yield Delta("Hello ")
        raise ProviderError("503 overloaded")

class SlowProvider:
    name = "slow"

    async def stream(self, messages):
        yield Delta("start ")
        await asyncio.sleep(10)
        yield Delta("never")

class BrokenProvider:
    name = "broken"

    async def stream(self, messages):
        raise RuntimeError("bug")
        yield Delta("unreachable")

class NoUsageProvider:
    name = "nousage"

    async def stream(self, messages):
        yield Delta("x" * 40)

class GenerationManagerTests(unittest.IsolatedAsyncioTestCase):
    async def test_streams_deltas_then_ends_and_saves_once(self):
        h = Harness(FakeProvider(delay=0, reply="one two three"))
        gid = h.start()
        await h.wait_idle()
        self.assertEqual(h.types(), ["assistant.delta"] * 3 + ["assistant.end"])
        end = h.sent[-1]["data"]
        self.assertEqual((end["generation_id"], end["status"], end["message_id"]), (gid, "completed", "msg_1"))
        self.assertEqual(len(h.saved), 1)
        self.assertEqual(h.saved[0][1], "one two three ")
        self.assertGreater(end["usage"]["output_tokens"], 0)

    async def test_cancel_keeps_the_partial_answer(self):
        h = Harness(FakeProvider(delay=0.02, reply="a b c d e f g h i j"))
        gid = h.start()
        await asyncio.sleep(0.07)
        self.assertTrue(await h.manager.cancel(gid))
        await h.wait_idle()
        self.assertEqual(h.sent[-1]["type"], "assistant.end")
        self.assertEqual(h.sent[-1]["data"]["status"], "canceled")
        self.assertEqual(len(h.saved), 1)
        self.assertEqual(h.saved[0][3], "canceled")
        self.assertLess(len(h.saved[0][1].split()), 10)           # not the full answer

    async def test_cancel_unknown_generation_returns_false(self):
        h = Harness(FakeProvider(delay=0))
        self.assertFalse(await h.manager.cancel("gen_nope"))

    async def test_provider_failure_sends_error_and_keeps_partial_text(self):
        h = Harness(FlakyProvider())
        h.start()
        await h.wait_idle()
        self.assertEqual(h.types(), ["assistant.delta", "assistant.error"])
        self.assertEqual(h.sent[-1]["data"]["code"], "upstream_unavailable")
        self.assertEqual(h.saved[0][3], "failed")

    async def test_timeout_is_reported(self):
        h = Harness(SlowProvider(), timeout=0.05)
        h.start()
        await h.wait_idle()
        self.assertEqual(h.sent[-1]["type"], "assistant.error")
        self.assertEqual(h.sent[-1]["data"]["code"], "generation_timeout")

    async def test_unexpected_exception_becomes_generic_error(self):
        h = Harness(BrokenProvider())
        h.start()
        await h.wait_idle()
        self.assertEqual(h.sent[-1]["data"]["code"], "generation_failed")
        self.assertEqual(h.saved, [])                                # nothing to store

    async def test_only_one_generation_at_a_time(self):
        h = Harness(FakeProvider(delay=0.01, reply="a b c"))
        first = h.start()
        with self.assertRaises(GenerationBusy):
            h.manager.reserve()
        await h.wait_idle()
        self.assertTrue(h.manager.reserve().startswith("gen_"))      # free again after the first finished
        self.assertTrue(first.startswith("gen_"))

    async def test_release_frees_an_unused_reservation(self):
        h = Harness(FakeProvider(delay=0))
        gid = h.manager.reserve()
        h.manager.release(gid)
        self.assertEqual(h.manager.active, 0)

    async def test_usage_is_estimated_when_provider_reports_none(self):
        h = Harness(NoUsageProvider())
        h.start()
        await h.wait_idle()
        usage = h.saved[0][2]
        self.assertEqual(usage.output_tokens, 10)                    # 40 characters / 4
        self.assertGreater(usage.input_tokens, 0)

    async def test_client_disconnect_stops_generation_and_saves_partial(self):
        h = Harness(FakeProvider(delay=0.01, reply="a b c d e f g h"))
        h.start()
        await asyncio.sleep(0.035)
        h.fail_sends = True                                          # the socket just died
        await h.wait_idle()
        self.assertEqual(h.saved[0][3], "canceled")
        self.assertLess(len(h.saved[0][1].split()), 8)

    async def test_cancel_all_on_disconnect(self):
        h = Harness(FakeProvider(delay=0.05, reply="a b c d e f g h"))
        h.start()
        await asyncio.sleep(0.06)
        await h.manager.cancel_all()
        self.assertEqual(h.manager.active, 0)
        self.assertEqual(len(h.saved), 1)

if __name__ == "__main__":
    unittest.main()
