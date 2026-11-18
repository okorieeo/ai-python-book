import asyncio
import json
import unittest

from .sse import HEARTBEAT, format_event, to_sse, with_heartbeat
from .dto import TextDelta, TurnFailed, TurnFinished, TurnStarted


def parse(raw: bytes):
    text = raw.decode()
    assert text.endswith("\n\n")
    lines = text[:-2].split("\n")
    assert lines[0].startswith("event: ") and lines[1].startswith("data: ") and len(lines) == 2, lines
    return lines[0][7:], json.loads(lines[1][6:])


class FormatTests(unittest.TestCase):
    def test_delta_roundtrip(self):
        self.assertEqual(parse(to_sse(TextDelta("Hi"))), ("delta", {"text": "Hi"}))

    def test_newlines_and_blank_lines_cannot_break_framing(self):
        nasty = "line one\n\nevent: error\ndata: forged\n\n"
        name, data = parse(to_sse(TextDelta(nasty)))
        self.assertEqual((name, data["text"]), ("delta", nasty))

    def test_unicode_is_kept_readable(self):
        self.assertIn("é 你好".encode(), to_sse(TextDelta("é 你好")))

    def test_all_event_kinds(self):
        self.assertEqual(parse(to_sse(TurnStarted(1, 2)))[0], "start")
        self.assertEqual(parse(to_sse(TurnFinished(2, "complete", "end_turn")))[1]["status"], "complete")
        err = parse(to_sse(TurnFailed(2, "provider_overloaded", "Busy", 5, True)))
        self.assertEqual(err[0], "error")
        self.assertEqual((err[1]["code"], err[1]["retry_after"], err[1]["partial"]), ("provider_overloaded", 5, True))

    def test_the_client_never_receives_cost_or_token_counts(self):
        body = to_sse(TurnFinished(2, "complete", "end_turn")).decode()
        for secret in ("cost", "token", "usage", "request_id"):
            self.assertNotIn(secret, body)

    def test_unknown_event_is_a_bug(self):
        with self.assertRaises(TypeError):
            to_sse(object())  # type: ignore[arg-type]

    def test_format_event_shape(self):
        self.assertEqual(format_event("x", {"a": 1}), b'event: x\ndata: {"a":1}\n\n')


class HeartbeatTests(unittest.IsolatedAsyncioTestCase):
    async def test_quiet_source_produces_heartbeats_then_real_data(self):
        async def slow():
            await asyncio.sleep(0.12)
            yield b"data-1"

        out = [c async for c in with_heartbeat(slow(), interval=0.03)]
        self.assertEqual(out[-1], b"data-1")
        self.assertGreaterEqual(out.count(HEARTBEAT), 2)

    async def test_fast_source_gets_no_heartbeats(self):
        async def fast():
            for i in range(3):
                yield f"c{i}".encode()

        out = [c async for c in with_heartbeat(fast(), interval=1.0)]
        self.assertEqual(out, [b"c0", b"c1", b"c2"])

    async def test_errors_from_the_source_propagate(self):
        async def broken():
            yield b"a"
            raise RuntimeError("boom")

        with self.assertRaises(RuntimeError):
            async for _ in with_heartbeat(broken(), interval=1.0):
                pass

    async def test_closing_early_closes_the_source(self):
        closed = []

        async def source():
            try:
                while True:
                    yield b"x"
                    await asyncio.sleep(0)
            finally:
                closed.append(True)

        gen = with_heartbeat(source(), interval=1.0)
        await gen.__anext__()
        await gen.aclose()
        self.assertEqual(closed, [True])


if __name__ == "__main__":
    unittest.main()
