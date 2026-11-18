"""Tests for the debugging toolkit of Chapter 40. Run: python -m unittest core.test_debugging -v"""
import asyncio
import json
import unittest

from core.debugging import asyncdebug as ad
from core.debugging import logtriage as lt
from core.debugging import nettiming as nt
from core.debugging import plancheck as pc
from core.debugging import sourcemap as sm
from core.debugging import sqlcheck as sq
from core.debugging import traceparse as tp

CHAINED = '''Traceback (most recent call last):
  File "/app/payments/gateways/paystack_gw.py", line 31, in _call
    response = requests.request(method, BASE + path, timeout=TIMEOUT, **kwargs)
  File "/usr/local/lib/python3.12/site-packages/requests/api.py", line 59, in request
    return session.request(method=method, url=url, **kwargs)
  File "/usr/local/lib/python3.12/site-packages/urllib3/connection.py", line 198, in _new_conn
    raise NewConnectionError(self, f"Failed to establish a new connection: {e}")
urllib3.exceptions.NewConnectionError: Failed to establish a new connection: [Errno 111] Connection refused

The above exception was the direct cause of the following exception:

Traceback (most recent call last):
  File "/app/payments/views.py", line 40, in post
    record = services.begin_checkout(user=request.user, idempotency_key=key, **data.validated_data)
  File "/app/payments/services.py", line 22, in begin_checkout
    return start_checkout(repo=repo, router=get_router(), gateways=get_gateways())
  File "/usr/local/lib/python3.12/site-packages/django/utils/functional.py", line 10, in inner
    return func(*args)
core.payments.gateway.GatewayUncertain: ConnectionError
'''

SIMPLE = '''Traceback (most recent call last):
  File "/app/chat/services.py", line 88, in send_message
    reply = provider.complete(turn.messages)
  File "/app/chat/providers.py", line 14, in complete
    return data["choices"][0]["text"]
KeyError: 'choices'
'''


class TracebackTests(unittest.TestCase):
    def test_simple_traceback(self):
        t = tp.parse_traceback(SIMPLE)
        self.assertEqual((t.final.exc_type, t.final.message), ("KeyError", "'choices'"))
        self.assertEqual(len(t.final.frames), 2)
        app = t.last_app_frame()
        self.assertEqual((app.file, app.line, app.func), ("/app/chat/providers.py", 14, "complete"))
        self.assertEqual(app.code, 'return data["choices"][0]["text"]')

    def test_chained_exceptions_root_and_final(self):
        t = tp.parse_traceback(CHAINED)
        self.assertEqual(len(t.chain), 2)
        self.assertEqual(t.root.exc_type, "urllib3.exceptions.NewConnectionError")
        self.assertEqual(t.final.exc_type, "core.payments.gateway.GatewayUncertain")
        self.assertEqual(t.root.link_to_next, "cause")

    def test_library_frames_are_skipped_for_your_code(self):
        t = tp.parse_traceback(CHAINED)
        self.assertEqual(t.last_app_frame().func, "begin_checkout")          # not the django frame
        self.assertEqual(t.last_app_frame(t.root).func, "_call")             # not requests/urllib3

    def test_summary_mentions_where_it_started(self):
        s = tp.parse_traceback(CHAINED).summary()
        self.assertIn("GatewayUncertain", s)
        self.assertIn("started as: urllib3.exceptions.NewConnectionError", s)
        self.assertIn("paystack_gw.py:31", s)

    def test_is_library(self):
        self.assertTrue(tp.Frame("/x/site-packages/a.py", 1, "f").is_library)
        self.assertFalse(tp.Frame("/app/a.py", 1, "f").is_library)

    def test_context_link(self):
        text = SIMPLE + "\nDuring handling of the above exception, another exception occurred:\n\n" + SIMPLE.replace("KeyError: 'choices'", "RuntimeError: boom")
        self.assertEqual(tp.parse_traceback(text).chain[0].link_to_next, "context")

    def test_exception_without_message(self):
        t = tp.parse_traceback('Traceback (most recent call last):\n  File "/app/a.py", line 1, in f\n    x()\nValueError\n')
        self.assertEqual((t.final.exc_type, t.final.message), ("ValueError", ""))


B64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"


def encode_vlq(n: int) -> str:
    v = (-n << 1) | 1 if n < 0 else n << 1
    out = ""
    while True:
        digit, v = v & 31, v >> 5
        out += B64[digit | (32 if v else 0)]
        if not v:
            return out


def make_map():
    # generated line 1: col 0 -> chat.ts 0:0 ; col 120 -> chat.ts line 41 col 4 "sendMessage" ; col 300 -> api.ts line 9 col 2
    segs = [(0, 0, 0, 0, None), (120, 0, 41, 4, 0), (300, 1, 9, 2, None)]
    prev = [0, 0, 0, 0, 0]
    parts, last_col = [], 0
    for gen, src, line, col, name in segs:
        fields = [gen - last_col, src - prev[1], line - prev[2], col - prev[3]]
        if name is not None:
            fields.append(name - prev[4]); prev[4] = name
        prev[1:4] = [src, line, col]
        last_col = gen
        parts.append("".join(encode_vlq(f) for f in fields))
    return {"version": 3, "sources": ["src/chat.ts", "src/api.ts"], "names": ["sendMessage"], "mappings": ",".join(parts)}


class SourceMapTests(unittest.TestCase):
    def test_vlq_known_values(self):
        self.assertEqual(sm.decode_vlq("AAAA"), [0, 0, 0, 0])
        self.assertEqual(sm.decode_vlq("gB"), [16])
        self.assertEqual(sm.decode_vlq("D"), [-1])
        for n in (0, 1, -1, 15, 16, -16, 1000, -1000, 123456):
            self.assertEqual(sm.decode_vlq(encode_vlq(n)), [n])

    def test_lookup(self):
        m = sm.SourceMap(make_map())
        self.assertEqual(m.lookup(1, 130), sm.Position("src/chat.ts", 42, 4, "sendMessage"))
        self.assertEqual(m.lookup(1, 120).source, "src/chat.ts")
        self.assertEqual(m.lookup(1, 5), sm.Position("src/chat.ts", 1, 0, None))
        self.assertEqual(m.lookup(1, 999), sm.Position("src/api.ts", 10, 2, None))

    def test_out_of_range(self):
        m = sm.SourceMap(make_map())
        self.assertIsNone(m.lookup(0, 1))
        self.assertIsNone(m.lookup(5, 1))

    def test_version_check(self):
        with self.assertRaises(ValueError):
            sm.SourceMap({"version": 2, "sources": [], "mappings": ""})

    def test_symbolicate_hermes_and_url_frames(self):
        maps = {"index.android.bundle": sm.SourceMap(make_map())}
        stack = ("TypeError: undefined is not a function\n"
                 "    at a (address at index.android.bundle:1:130)\n"
                 "    at b (http://10.0.2.2:8081/index.android.bundle?platform=android:1:305)\n"
                 "    at c (native)\n"
                 "    at d (other.bundle:1:5)")
        out = sm.symbolicate(stack, maps)
        self.assertEqual(out[0], "TypeError: undefined is not a function")
        self.assertEqual(out[1], "at sendMessage (src/chat.ts:42:4)")
        self.assertEqual(out[2], "at b (src/api.ts:10:2)")
        self.assertEqual(out[3].strip(), "at c (native)")
        self.assertEqual(out[4].strip(), "at d (other.bundle:1:5)")


def jl(**kw):
    return json.dumps(kw)


LOGS = [
    jl(time="2026-11-06T10:00:00.100Z", level="INFO", event="request_started", request_id="r1", fields={"path": "/api/v1/chat/"}),
    jl(time="2026-11-06T10:00:00.300Z", level="INFO", event="turn_prepared", request_id="r1", fields={"redactions": 2}),
    jl(time="2026-11-06T10:00:02.900Z", level="ERROR", event="provider_timeout", request_id="r1", fields={"provider": "x"}),
    jl(time="2026-11-06T10:00:03.000Z", level="INFO", event="request_finished", request_id="r1", fields={"status": 503, "duration_ms": 2900}),
    jl(time="2026-11-06T10:00:01.000Z", level="INFO", event="request_started", request_id="r2", fields={}),
    jl(time="2026-11-06T10:00:01.050Z", level="INFO", event="request_finished", request_id="r2", fields={"status": 200, "duration_ms": 50}),
    "Traceback (most recent call last):",
    "",
    jl(time="2026-11-06T10:00:04.000Z", level="WARNING", event="slow_query", request_id="r3", fields={"duration_ms": 1500}),
]


class LogTests(unittest.TestCase):
    def test_parse_counts_non_json(self):
        entries, skipped = lt.parse_lines(LOGS)
        self.assertEqual((len(entries), skipped), (7, 1))

    def test_group_and_order_by_time(self):
        tl = lt.triage(LOGS)["timelines"]
        self.assertEqual(sorted(tl), ["r1", "r2", "r3"])
        self.assertEqual([e.event for e in tl["r1"].entries], ["request_started", "turn_prepared", "provider_timeout", "request_finished"])

    def test_failing_and_slow(self):
        r = lt.triage(LOGS)
        self.assertEqual(r["failing"], ["r1"])
        self.assertEqual(r["slow"], ["r1", "r3"])
        self.assertEqual(r["timelines"]["r1"].first_error.event, "provider_timeout")

    def test_render(self):
        text = lt.render(lt.triage(LOGS)["timelines"]["r1"])
        self.assertIn("request r1", text)
        self.assertIn("provider_timeout", text)
        self.assertIn("redactions=2", text)

    def test_missing_request_id_is_grouped(self):
        r = lt.triage([jl(time="t", level="INFO", event="x")])
        self.assertEqual(list(r["timelines"]), ["-"])


class SqlTests(unittest.TestCase):
    def test_fingerprint_ignores_values(self):
        a = sq.fingerprint('SELECT * FROM msg WHERE conversation_id = 42 AND name = \'Ada\'')
        b = sq.fingerprint('SELECT * FROM msg WHERE conversation_id = 7 AND name = \'O\'\'Neil\'')
        self.assertEqual(a, b)
        self.assertEqual(sq.fingerprint('SELECT 1 WHERE id IN (1, 2, 3)'), sq.fingerprint('SELECT 1 WHERE id IN (9)'))
        self.assertEqual(sq.fingerprint('SELECT 1 WHERE id = %s'), sq.fingerprint('SELECT 1 WHERE id = 5'))

    def test_n_plus_one_found(self):
        queries = ['SELECT * FROM conversation'] + [f'SELECT * FROM message WHERE conversation_id = {i}' for i in range(30)]
        repeats = sq.find_repeats(queries)
        self.assertEqual((len(repeats), repeats[0].count), (1, 30))
        self.assertTrue(sq.verdict(queries, budget=5).startswith("N+1 suspected: 30 x"))

    def test_budget_and_ok(self):
        three = ["SELECT a FROM t1", "SELECT b FROM t2", "SELECT c FROM t3"]
        self.assertEqual(sq.verdict(three, budget=3), "ok")
        self.assertIn("over budget", sq.verdict(three, budget=2))

    def test_threshold(self):
        q = [f"SELECT * FROM m WHERE id = {i}" for i in range(4)]
        self.assertEqual(sq.find_repeats(q, threshold=5), [])


SEQ = '''Seq Scan on chat_message  (cost=0.00..18334.00 rows=1 width=120) (actual time=0.012..95.331 rows=40000 loops=1)
  Filter: (conversation_id = 42)
  Rows Removed by Filter: 960000
Planning Time: 0.110 ms
Execution Time: 1234.500 ms
'''
GOOD = '''Index Scan using chat_message_conversation_idx on chat_message  (cost=0.42..8.44 rows=30 width=120) (actual time=0.020..0.080 rows=28 loops=1)
  Index Cond: (conversation_id = 42)
Planning Time: 0.090 ms
Execution Time: 0.150 ms
'''
LOOPY = '''Nested Loop  (cost=0.42..99999.00 rows=5000 width=64) (actual time=0.1..800.0 rows=5000 loops=1)
  ->  Seq Scan on chat_conversation  (cost=0.00..100.00 rows=5000 width=8) (actual time=0.01..5.0 rows=5000 loops=1)
  ->  Index Scan using msg_idx on chat_message  (cost=0.42..2.00 rows=1 width=56) (actual time=0.01..0.02 rows=1 loops=5000)
Execution Time: 810.000 ms
'''
SORT = '''Sort  (cost=1.00..2.00 rows=100 width=8) (actual time=1.0..900.0 rows=100 loops=1)
  Sort Key: created_at
  Sort Method: external merge  Disk: 51200kB
'''


class PlanTests(unittest.TestCase):
    def test_seq_scan_problems(self):
        f = pc.analyze(SEQ)
        kinds = {(x.severity, x.node) for x in f}
        self.assertIn(("high", "Seq Scan on chat_message"), kinds)
        self.assertTrue(any("planner expected 1 rows but got 40,000" in x.message for x in f))
        self.assertTrue(any("960,000 rows" in x.message for x in f))
        self.assertTrue(any(x.severity == "info" and x.message.startswith("execution took 1,23") for x in f))

    def test_good_plan_has_no_findings(self):
        self.assertEqual(pc.analyze(GOOD), [])

    def test_inner_loop_executed_thousands_of_times(self):
        f = pc.analyze(LOOPY)
        self.assertTrue(any("executed 5,000 times" in x.message for x in f))

    def test_sort_spill(self):
        self.assertTrue(any(x.node == "Sort" and "spilled" in x.message for x in pc.analyze(SORT)))


class NetTests(unittest.TestCase):
    def test_parse_and_phases(self):
        t = nt.Timing.parse("dns=0.020 connect=0.080 tls=0.200 ttfb=2.300 total=2.400 code=200 size=1500")
        p = t.phases()
        self.assertAlmostEqual(p["tcp_connect"], 0.06)
        self.assertAlmostEqual(p["tls_handshake"], 0.12)
        self.assertAlmostEqual(p["server_wait"], 2.1)
        self.assertAlmostEqual(p["download"], 0.1)

    def test_slow_server_is_not_a_network_problem(self):
        t = nt.Timing.parse("dns=0.020 connect=0.080 tls=0.200 ttfb=2.300 total=2.400 code=200 size=1500")
        notes = nt.diagnose(t)
        self.assertEqual(len(notes), 1)
        self.assertIn("app or database is slow, not the network", notes[0])

    def test_connection_failure(self):
        t = nt.Timing.parse("dns=0.000 connect=0.000 tls=0.000 ttfb=0.000 total=0.000 code=000 size=0")
        self.assertIn("no HTTP response", nt.diagnose(t)[0])

    def test_dns_and_auth(self):
        t = nt.Timing.parse("dns=1.500 connect=1.520 tls=1.600 ttfb=1.700 total=1.700 code=401 size=40")
        notes = " | ".join(nt.diagnose(t))
        self.assertIn("DNS took 1.50s", notes)
        self.assertIn("authentication or permission", notes)

    def test_healthy(self):
        t = nt.Timing.parse("dns=0.010 connect=0.030 tls=0.080 ttfb=0.150 total=0.160 code=200 size=900")
        self.assertEqual(nt.diagnose(t), ["no obvious problem in the timings"])

    def test_plain_http_without_tls(self):
        t = nt.Timing.parse("dns=0.010 connect=0.030 tls=0.000 ttfb=1.500 total=1.510 code=200 size=10")
        self.assertAlmostEqual(t.phases()["tls_handshake"], 0.0)
        self.assertAlmostEqual(t.phases()["server_wait"], 1.47)


class AsyncTests(unittest.TestCase):
    def test_forgotten_await_is_detected(self):
        async def save():
            return 1

        async def handler():
            save()                      # BUG: no await, the coroutine never runs

        with ad.collect_unawaited() as found:
            asyncio.run(handler())
        self.assertEqual(len(found), 1)
        self.assertIn("save", found[0])

    def test_correct_code_has_no_warning(self):
        async def save():
            return 1

        async def handler():
            return await save()

        with ad.collect_unawaited() as found:
            self.assertEqual(asyncio.run(handler()), 1)
        self.assertEqual(found, [])

    def test_blocking_call_is_reported_in_debug_mode(self):
        async def bad():
            ad.blocking_call(0.15)

        msgs = ad.run_with_slow_callback_detection(bad(), threshold=0.05)
        self.assertTrue(msgs)
        self.assertIn("took 0.1", msgs[0])

    def test_awaited_sleep_is_not_reported(self):
        async def good():
            await asyncio.sleep(0.15)

        self.assertEqual(ad.run_with_slow_callback_detection(good(), threshold=0.05), [])

    def test_describe_tasks(self):
        async def worker():
            await asyncio.sleep(10)

        async def main():
            t = asyncio.create_task(worker(), name="worker-1")
            await asyncio.sleep(0)
            rows = ad.describe_tasks()
            t.cancel()
            return rows

        rows = asyncio.run(main())
        self.assertTrue(any(r.startswith("worker-1") and "pending" in r and "worker" in r for r in rows))


if __name__ == "__main__":
    unittest.main()
