"""Tests for Chapter 55's framework-independent modules (no Django, Sentry or Docker needed).

    cd backend && python -m unittest core.test_observability -v
"""
import io
import json
import logging
import threading
import time
import unittest
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer

from core.observability import costguard, heartbeat as hb, logalerts, readiness, request_log, sentry_scrub


# ------------------------------------------------------------------ readiness
class ReadinessTests(unittest.TestCase):
    def test_all_passing(self):
        results = readiness.run_checks({"db": lambda: None, "redis": lambda: None})
        self.assertTrue(readiness.overall_ok(results))
        self.assertEqual(readiness.public_payload(results), {"status": "ok"})

    def test_one_failure_makes_it_unavailable_and_names_only_the_class(self):
        def boom():
            raise ConnectionError("postgres://chat:hunter2@db/chat refused")
        results = readiness.run_checks({"db": boom, "redis": lambda: None})
        self.assertFalse(readiness.overall_ok(results))
        failed = [r for r in results if not r.ok][0]
        self.assertEqual((failed.name, failed.detail), ("db", "ConnectionError"))
        self.assertNotIn("hunter2", json.dumps(readiness.detail_payload(results)))

    def test_public_payload_reveals_nothing_about_internals(self):
        results = readiness.run_checks({"db": lambda: 1 / 0})
        self.assertEqual(readiness.public_payload(results), {"status": "unavailable"})
        detail = readiness.detail_payload(results)
        self.assertEqual(detail["checks"]["db"]["detail"], "ZeroDivisionError")

    def test_a_hung_check_cannot_hang_the_endpoint(self):
        release = threading.Event()
        started = time.monotonic()
        results = readiness.run_checks({"slow": lambda: release.wait(5), "fast": lambda: None}, timeout=0.3)
        elapsed = time.monotonic() - started
        release.set()
        self.assertLess(elapsed, 1.5)
        by_name = {r.name: r for r in results}
        self.assertFalse(by_name["slow"].ok)
        self.assertIn("timed out", by_name["slow"].detail)
        self.assertTrue(by_name["fast"].ok)

    def test_checks_run_in_parallel_within_one_timeout(self):
        started = time.monotonic()
        readiness.run_checks({f"c{i}": (lambda: time.sleep(0.3)) for i in range(4)}, timeout=2)
        self.assertLess(time.monotonic() - started, 0.9)

    def test_empty_checks(self):
        self.assertEqual(readiness.run_checks({}), [])
        self.assertTrue(readiness.overall_ok([]))

    def test_factories(self):
        class Cursor:
            def __init__(self): self.sql = []
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def execute(self, sql): self.sql.append(sql)
            def fetchone(self): return (1,)
        class Conn:
            def __init__(self): self.c = Cursor()
            def cursor(self): return self.c
        conn = Conn()
        conn.closed = 0
        conn.close = lambda: setattr(conn, "closed", conn.closed + 1)
        readiness.database_check(conn)()
        self.assertEqual((conn.c.sql, conn.closed), (["SELECT 1"], 0))
        readiness.database_check(conn, close_after=True)()
        self.assertEqual(conn.closed, 1)

        class Broken(Conn):
            def cursor(self): raise OSError("down")
        broken = Broken()
        broken.closed = 0
        broken.close = lambda: setattr(broken, "closed", 1)
        with self.assertRaises(OSError):
            readiness.database_check(broken, close_after=True)()
        self.assertEqual(broken.closed, 1)  # closed even when the check fails
        class R:
            def __init__(self, pong, depth=0): self.pong, self.depth = pong, depth
            def ping(self): return self.pong
            def llen(self, key): self.key = key; return self.depth
        readiness.redis_check(R(True))()
        with self.assertRaises(RuntimeError):
            readiness.redis_check(R(False))()
        readiness.queue_depth_check(R(True, depth=10), max_depth=100)()
        busy = R(True, depth=500)
        with self.assertRaises(RuntimeError):
            readiness.queue_depth_check(busy, queue="celery", max_depth=100)()
        self.assertEqual(busy.key, "celery")


# ------------------------------------------------------------------ sentry scrubbing
def sample_event():
    return {
        "message": "failed with Authorization: Bearer abc.def.ghi",
        "request": {
            "url": "https://api.example.com/api/chat/",
            "method": "POST",
            "data": {"messages": [{"role": "user", "content": "my medical question"}]},
            "cookies": {"sessionid": "s3cr3t"},
            "query_string": "token=abc",
            "headers": {"Authorization": "Bearer abc", "Cookie": "sessionid=1", "User-Agent": "x", "X-Forwarded-For": "1.2.3.4"},
            "env": {"REMOTE_ADDR": "1.2.3.4", "SERVER_NAME": "api"},
        },
        "user": {"id": "42", "email": "a@b.co", "ip_address": "1.2.3.4", "username": "ada"},
        "extra": {"prompt": "secret question", "model": "m1", "input_tokens": 120, "api_key": "sk_live_abc",
                  "nested": {"completion": "answer", "ok": 1}},
        "contexts": {"ai": {"messages": ["hi"], "latency_ms": 90}},
        "breadcrumbs": {"values": [{"message": "password=hunter2 sent", "data": {"token": "t", "n": 1}}]},
        "exception": {"values": [{"type": "ValueError", "value": "bad password=hunter2",
                                  "stacktrace": {"frames": [{"function": "f", "vars": {"prompt": "x"}}]}}]},
    }


class SentryScrubTests(unittest.TestCase):
    def setUp(self):
        self.event = sentry_scrub.scrub_event(sample_event(), redact_text=lambda t: t.replace("hunter2", "[X]"))

    def test_request_body_cookies_and_query_are_removed(self):
        req = self.event["request"]
        for gone in ("data", "cookies", "query_string"):
            self.assertNotIn(gone, req)
        self.assertEqual(req["url"], "https://api.example.com/api/chat/")
        self.assertEqual(req["method"], "POST")

    def test_sensitive_headers_and_client_ip_are_masked(self):
        headers = self.event["request"]["headers"]
        self.assertEqual(headers["Authorization"], "[REDACTED]")
        self.assertEqual(headers["Cookie"], "[REDACTED]")
        self.assertEqual(headers["X-Forwarded-For"], "[REDACTED]")
        self.assertEqual(headers["User-Agent"], "x")
        self.assertNotIn("REMOTE_ADDR", self.event["request"]["env"])

    def test_user_is_reduced_to_an_id(self):
        self.assertEqual(self.event["user"], {"id": "42"})

    def test_chat_content_and_credentials_are_removed_but_counters_survive(self):
        extra = self.event["extra"]
        self.assertEqual(extra["prompt"], "[CONTENT REMOVED]")
        self.assertEqual(extra["api_key"], "[REDACTED]")
        self.assertEqual(extra["nested"], {"completion": "[CONTENT REMOVED]", "ok": 1})
        self.assertEqual((extra["model"], extra["input_tokens"]), ("m1", 120))
        self.assertEqual(self.event["contexts"]["ai"], {"messages": "[CONTENT REMOVED]", "latency_ms": 90})

    def test_token_counters_survive_but_token_secrets_do_not(self):
        data = {"input_tokens": 5, "output_tokens": 6, "total_tokens": 11, "max_tokens": 100, "cache_read_input_tokens": 3,
                "access_token": "a", "token": "b", "refresh_token": "c", "api_token": "d"}
        out = sentry_scrub.scrub_value(data)
        self.assertEqual([out[k] for k in ("input_tokens", "output_tokens", "total_tokens", "max_tokens", "cache_read_input_tokens")],
                         [5, 6, 11, 100, 3])
        for secret in ("access_token", "token", "refresh_token", "api_token"):
            self.assertEqual(out[secret], "[REDACTED]", secret)

    def test_breadcrumbs_exceptions_and_messages_are_redacted(self):
        crumb = self.event["breadcrumbs"]["values"][0]
        self.assertEqual(crumb["message"], "password=[X] sent")
        self.assertEqual(crumb["data"], {"token": "[REDACTED]", "n": 1})
        exc = self.event["exception"]["values"][0]
        self.assertEqual(exc["value"], "bad password=[X]")
        self.assertNotIn("vars", exc["stacktrace"]["frames"][0])

    def test_nothing_sensitive_is_left_anywhere_in_the_event(self):
        text = json.dumps(self.event)
        for leaked in ("my medical question", "s3cr3t", "sk_live_abc", "a@b.co", "1.2.3.4", "secret question", "hunter2"):
            self.assertNotIn(leaked, text)

    def test_odd_events_do_not_crash_the_scrubber(self):
        for event in ({}, {"request": None}, {"user": None}, {"exception": None}, {"breadcrumbs": []}, {"extra": "x"}):
            sentry_scrub.scrub_event(event)

    def test_default_redactor_masks_bearer_tokens(self):
        out = sentry_scrub.scrub_event({"message": "Authorization: Bearer abcdef"})
        self.assertNotIn("abcdef", out["message"])

    def test_works_with_chapter_17s_real_redaction_module(self):
        try:
            from core.security.redaction import redact  # noqa: F401
        except ImportError:
            self.skipTest("Chapter 17's core.security.redaction is not on the path")
        out = sentry_scrub.scrub_event({"message": "retry with password=hunter2 and Authorization: Bearer abc.def.ghi"})
        self.assertNotIn("hunter2", out["message"])
        self.assertNotIn("abc.def.ghi", out["message"])

    def test_init_without_a_dsn_does_nothing(self):
        class Boom:
            def init(self, **kw): raise AssertionError("must not be called")
        self.assertFalse(sentry_scrub.init_sentry("", environment="production", release="a1", sdk=Boom()))
        self.assertFalse(sentry_scrub.init_sentry(None, environment="production", release="a1", sdk=Boom()))

    def test_init_passes_the_privacy_settings(self):
        seen = {}
        class Fake:
            def init(self, **kw): seen.update(kw)
        ok = sentry_scrub.init_sentry("https://k@o0.ingest.sentry.io/1", environment="production",
                                      release="a1b2c3d", traces_sample_rate=0.05, sdk=Fake())
        self.assertTrue(ok)
        self.assertIs(seen["send_default_pii"], False)
        self.assertEqual(seen["max_request_body_size"], "never")
        self.assertIs(seen["include_local_variables"], False)
        self.assertEqual((seen["environment"], seen["release"], seen["traces_sample_rate"]), ("production", "a1b2c3d", 0.05))
        self.assertIs(seen["before_send"], sentry_scrub.scrub_event)
        self.assertIs(seen["before_send_transaction"], sentry_scrub.scrub_event)


# ------------------------------------------------------------------ heartbeat
class _Hits(BaseHTTPRequestHandler):
    paths: list = []
    status = 200

    def do_GET(self):  # noqa: N802
        type(self).paths.append(self.path)
        self.send_response(type(self).status)
        self.end_headers()

    def log_message(self, *a):
        pass


class HeartbeatTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), _Hits)
        cls.url = f"http://127.0.0.1:{cls.server.server_address[1]}/abc-uuid"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        _Hits.paths = []
        _Hits.status = 200

    def test_ping_and_suffixes(self):
        self.assertTrue(hb.ping(self.url, require_https=False))
        self.assertTrue(hb.ping(self.url + "/", "/fail", require_https=False))
        self.assertEqual(_Hits.paths, ["/abc-uuid", "/abc-uuid/fail"])

    def test_https_is_required_by_default(self):
        self.assertFalse(hb.ping(self.url))
        self.assertEqual(_Hits.paths, [])

    def test_no_url_and_unreachable_never_raise(self):
        self.assertFalse(hb.ping(None))
        self.assertFalse(hb.ping(""))
        self.assertFalse(hb.ping("http://127.0.0.1:1/x", require_https=False, timeout=0.5))

    def test_server_errors_are_not_success(self):
        _Hits.status = 500
        self.assertFalse(hb.ping(self.url, require_https=False))

    def test_context_manager_success_sequence(self):
        with hb.heartbeat(self.url, require_https=False):
            pass
        self.assertEqual(_Hits.paths, ["/abc-uuid/start", "/abc-uuid"])

    def test_context_manager_failure_sends_fail_and_reraises(self):
        with self.assertRaises(ValueError):
            with hb.heartbeat(self.url, require_https=False):
                raise ValueError("boom")
        self.assertEqual(_Hits.paths, ["/abc-uuid/start", "/abc-uuid/fail"])

    def test_a_dead_monitor_does_not_break_the_job(self):
        ran = []
        with hb.heartbeat("http://127.0.0.1:1/x", require_https=False, timeout=0.3):
            ran.append(1)
        self.assertEqual(ran, [1])

    def test_the_url_is_never_logged(self):
        with self.assertLogs("heartbeat", level="WARNING") as captured:
            hb.ping("http://127.0.0.1:1/secret-uuid-123", require_https=False, timeout=0.3)
        self.assertNotIn("secret-uuid-123", "\n".join(captured.output))


# ------------------------------------------------------------------ request log
class FakeUser:
    def __init__(self, pk=None, auth=False): self.pk, self.is_authenticated = pk, auth


class FakeRequest:
    def __init__(self, path, method="GET", user=None): self.path, self.method, self.user = path, method, user


class FakeResponse:
    def __init__(self, status): self.status_code = status


class RequestLogTests(unittest.TestCase):
    def test_normalize_path(self):
        n = request_log.normalize_path
        self.assertEqual(n("/api/conversations/42/"), "/api/conversations/:id/")
        self.assertEqual(n("/api/c/8f14e45f-ceea-467a-9a36-2c7a2d5a1f00/messages/"), "/api/c/:id/messages/")
        self.assertEqual(n("/reset/abcdefghijklmnopqrstuvwxyz0123/"), "/reset/:token/")
        self.assertEqual(n("/api/search/?q=secret&token=abc"), "/api/search/")
        self.assertEqual(n("/api/v2/users/"), "/api/v2/users/")

    def run_one(self, request, status=200, raises=None):
        ticks = iter([10.0, 10.25])
        logger = logging.getLogger("http-test")
        def get_response(req):
            if raises:
                raise raises
            return FakeResponse(status)
        mw = request_log.RequestLogMiddleware(get_response, logger=logger, clock=lambda: next(ticks))
        with self.assertLogs("http-test", level="DEBUG") as captured:
            try:
                mw(request)
            except Exception:
                pass
            logger.debug("sentinel")  # assertLogs fails if nothing is logged
        return [r for r in captured.records if r.getMessage() == "request"]

    def test_logs_the_fields_chapter_17s_formatter_expects(self):
        records = self.run_one(FakeRequest("/api/conversations/7/", "DELETE", FakeUser(5, True)), 204)
        self.assertEqual(len(records), 1)
        rec = records[0]
        self.assertEqual(rec.event, "http_request")
        self.assertEqual(rec.fields, {"method": "DELETE", "path": "/api/conversations/:id/", "status": 204, "ms": 250, "user_id": "5"})
        self.assertEqual(rec.levelno, logging.INFO)

    def test_anonymous_users_and_server_errors(self):
        rec = self.run_one(FakeRequest("/api/x/", user=FakeUser(None, False)), 502)[0]
        self.assertIsNone(rec.fields["user_id"])
        self.assertEqual(rec.levelno, logging.ERROR)

    def test_an_unhandled_exception_is_logged_as_500_and_reraised(self):
        ticks = iter([1.0, 1.1])
        mw = request_log.RequestLogMiddleware(lambda r: (_ for _ in ()).throw(RuntimeError("x")),
                                              logger=logging.getLogger("http-test2"), clock=lambda: next(ticks))
        with self.assertLogs("http-test2") as captured:
            with self.assertRaises(RuntimeError):
                mw(FakeRequest("/api/boom/"))
        self.assertEqual(captured.records[0].fields["status"], 500)

    def test_health_checks_are_not_logged(self):
        logger = logging.getLogger("http-test3")
        mw = request_log.RequestLogMiddleware(lambda r: FakeResponse(200), logger=logger)
        with self.assertNoLogs("http-test3"):
            mw(FakeRequest("/healthz/"))
            mw(FakeRequest("/readyz/"))

    def test_missing_user_attribute_is_fine(self):
        class Bare:
            path, method = "/api/a/", "GET"
        mw = request_log.RequestLogMiddleware(lambda r: FakeResponse(200), logger=logging.getLogger("http-test4"))
        with self.assertLogs("http-test4") as captured:
            mw(Bare())
        self.assertIsNone(captured.records[0].fields["user_id"])


# ------------------------------------------------------------------ log alerts
def req(status, user="u1", ms=50):
    return {"event": "http_request", "fields": {"method": "GET", "path": "/x/", "status": status, "ms": ms, "user_id": user}}


def names(alerts):
    return {a.name for a in alerts}


class LogAlertTests(unittest.TestCase):
    def test_quiet_traffic_has_no_alerts(self):
        self.assertEqual(logalerts.evaluate([req(200) for _ in range(200)] + [req(404, "u2")]), [])

    def test_parse_lines_handles_docker_prefixes_and_junk(self):
        lines = ['backend-1  | {"event": "http_request", "fields": {"status": 200}}', "plain text", "{broken",
                 '{"event": "login_failed"}', '["not", "a dict"]', ""]
        parsed = logalerts.parse_lines(lines)
        self.assertEqual([e.get("event") for e in parsed], ["http_request", "login_failed"])

    def test_auth_failures_combine_login_events_and_401s(self):
        entries = [{"event": "login_failed"}] * 12 + [req(401)] * 8
        self.assertIn("auth_failures", names(logalerts.evaluate(entries)))
        self.assertNotIn("auth_failures", names(logalerts.evaluate(entries[:-1])))

    def test_probing_is_counted_per_user(self):
        spread = [req(404, f"u{i}") for i in range(60)]
        self.assertEqual(logalerts.evaluate(spread), [])
        focused = [req(403, "mallory")] * 20 + [req(404, "mallory")] * 10
        self.assertEqual(names(logalerts.evaluate(focused)), {"probing_by_mallory"})

    def test_anonymous_probing_is_counted_together(self):
        self.assertIn("probing_by_anonymous", names(logalerts.evaluate([req(404, None)] * 30)))

    def test_rate_limited(self):
        self.assertIn("rate_limited", names(logalerts.evaluate([req(429)] * 50)))

    def test_server_errors_by_count_and_by_ratio(self):
        self.assertIn("server_errors", names(logalerts.evaluate([req(500)] * 5)))
        by_ratio = [req(200)] * 940 + [req(503)] * 4  # under the count, under the ratio
        self.assertNotIn("server_errors", names(logalerts.evaluate(by_ratio, {"server_errors": 5})))
        ratio_case = [req(200)] * 95 + [req(500)] * 4 + [req(200)]
        self.assertIn("server_errors", names(logalerts.evaluate(ratio_case, {"server_errors": 50, "server_error_ratio": 0.04})))

    def test_ratio_is_not_judged_on_tiny_samples(self):
        self.assertEqual(logalerts.evaluate([req(500), req(200)], {"server_errors": 5}), [])

    def test_slow_p95_needs_enough_requests(self):
        slow = [req(200, ms=3000)] * 60
        self.assertIn("slow_requests_p95_ms", names(logalerts.evaluate(slow)))
        self.assertEqual(logalerts.evaluate([req(200, ms=3000)] * 10), [])
        mostly_fast = [req(200, ms=40)] * 95 + [req(200, ms=9000)] * 4
        self.assertNotIn("slow_requests_p95_ms", names(logalerts.evaluate(mostly_fast)))

    def test_webhook_signature_failures(self):
        self.assertIn("webhook_signature_failures",
                      names(logalerts.evaluate([{"event": "webhook_signature_failed"}] * 3)))

    def test_thresholds_can_be_overridden(self):
        self.assertIn("rate_limited", names(logalerts.evaluate([req(429)] * 3, {"rate_limited": 3})))

    def test_main_prints_and_sets_the_exit_code(self):
        out = io.StringIO()
        lines = [json.dumps(req(429))] * 50
        self.assertEqual(logalerts.main(stdin=iter(lines), out=out), 1)
        self.assertIn("ALERT rate_limited: 50", out.getvalue())
        out = io.StringIO()
        self.assertEqual(logalerts.main(stdin=iter([json.dumps(req(200))]), out=out), 0)
        self.assertTrue(out.getvalue().startswith("OK"))

    def test_works_on_the_output_of_the_request_middleware_and_json_formatter(self):
        """End to end: middleware -> record -> a Chapter 17 style JSON line -> alert."""
        lines = []
        for _ in range(55):
            rec = logging.LogRecord("http", logging.INFO, "f", 1, "request", None, None)
            rec.event, rec.fields = "http_request", {"method": "POST", "path": "/api/chat/", "status": 429, "ms": 5, "user_id": "9"}
            lines.append(json.dumps({"level": rec.levelname, "message": rec.getMessage(), "event": rec.event, "fields": rec.fields}))
        self.assertIn("rate_limited", names(logalerts.evaluate(logalerts.parse_lines(lines))))


# ------------------------------------------------------------------ cost guard
PRICES = {"small": {"input": 1.0, "output": 3.0}, "large": {"input": 5.0, "output": 20.0}}
TODAY = date(2026, 11, 10)


def rows(*items):
    return [costguard.Usage(d, m, i, o) for d, m, i, o in items]


class CostGuardTests(unittest.TestCase):
    def test_cost_is_per_million_tokens(self):
        self.assertAlmostEqual(costguard.cost(costguard.Usage(TODAY, "small", 2_000_000, 1_000_000), PRICES), 5.0)
        self.assertAlmostEqual(costguard.cost(costguard.Usage(TODAY, "large", 100_000, 50_000), PRICES), 1.5)

    def test_unknown_models_are_reported_not_free(self):
        totals, unknown = costguard.daily_totals(rows((TODAY, "mystery", 10**9, 10**9)), PRICES)
        self.assertEqual((totals, unknown), ({}, {"mystery"}))
        self.assertTrue(any("unknown_models" in a for a in costguard.evaluate(totals, unknown, TODAY, 100, 1000)))

    def test_daily_budget(self):
        totals = {TODAY: 25.0}
        alerts = costguard.evaluate(totals, set(), TODAY, daily_budget=20, monthly_budget=10_000)
        self.assertTrue(any("daily_budget" in a for a in alerts))
        self.assertEqual(costguard.evaluate({TODAY: 5.0}, set(), TODAY, 20, 10_000), [])

    def test_projection_uses_spend_so_far_plus_recent_average(self):
        totals = {date(2026, 11, d): 10.0 for d in range(1, 10)}  # 9 days x 10
        # 9 days spent (90) + average of the previous 7 days (10) x 20 remaining days after today
        self.assertAlmostEqual(costguard.projected_month(totals, TODAY), 90 + 10 * 20)

    def test_projection_alert(self):
        totals = {date(2026, 11, d): 10.0 for d in range(1, 10)}
        alerts = costguard.evaluate(totals, set(), TODAY, daily_budget=50, monthly_budget=250)
        self.assertTrue(any("monthly_projection" in a for a in alerts))

    def test_month_boundaries(self):
        dec = date(2026, 12, 31)
        self.assertAlmostEqual(costguard.projected_month({dec: 1.0}, dec), 1.0)
        feb = date(2027, 2, 27)
        self.assertEqual(costguard.projected_month({}, feb), 0.0)

    def test_spike_detection(self):
        totals = {TODAY - timedelta(days=i): 10.0 for i in range(1, 8)}
        totals[TODAY] = 35.0
        alerts = costguard.evaluate(totals, set(), TODAY, daily_budget=1000, monthly_budget=10**6)
        self.assertTrue(any("spike" in a and "3.5x" in a for a in alerts))

    def test_no_history_means_no_spike_alert(self):
        self.assertEqual(costguard.evaluate({TODAY: 5.0}, set(), TODAY, 100, 10**6), [])

    def test_load_usage_and_cli(self):
        import csv
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            usage = os.path.join(tmp, "u.csv")
            with open(usage, "w", newline="") as f:
                w = csv.writer(f)
                w.writerow(["day", "model", "input_tokens", "output_tokens"])
                w.writerow([TODAY.isoformat(), "small", 10_000_000, 5_000_000])
            prices = os.path.join(tmp, "p.json")
            with open(prices, "w") as f:
                json.dump({"_note": "x", **PRICES}, f)
            out = io.StringIO()
            code = costguard.main([usage, prices, "--daily", "10", "--monthly", "1000"], today=TODAY, out=out)
            self.assertEqual(code, 1)  # 10 + 15 = 25 > 10
            self.assertIn("today 25.00", out.getvalue())
            self.assertEqual(costguard.main([usage, prices, "--daily", "100", "--monthly", "100000"], today=TODAY, out=io.StringIO()), 0)


if __name__ == "__main__":
    unittest.main()
