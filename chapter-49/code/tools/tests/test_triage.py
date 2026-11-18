import unittest
from pathlib import Path

from tools import triage

SAMPLES = Path(__file__).parent / "samples"
PY = (SAMPLES / "python_trace.txt").read_text()
NODE = (SAMPLES / "node_trace.txt").read_text()
NODE2 = (SAMPLES / "node_stack2.txt").read_text()


class RedactTests(unittest.TestCase):
    def test_bearer_token_and_email(self):
        out = triage.redact(PY)
        self.assertNotIn("abc123def456ghi789jkl012", out)
        self.assertNotIn("ada@example.com", out)
        self.assertIn("Bearer [REDACTED]", out)

    def test_assignments_and_urls(self):
        out = triage.redact("DATABASE_URL=postgres://aichat:hunter2@db:5432/x password=hunter3 api_key: 'k-1' SECRET_KEY=abc")
        for leaked in ("hunter2", "hunter3", "k-1", "=abc"):
            self.assertNotIn(leaked, out)
        self.assertIn("postgres://aichat:[REDACTED]@db", out)

    def test_jwt_and_provider_keys(self):
        jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dBjftJeZ4CVPmB92K27uhbUJU1p1r"
        out = triage.redact(f"token {jwt} key sk-live-abcdefghijklmnop1234")
        self.assertNotIn("eyJhbGci", out)
        self.assertNotIn("abcdefghijklmnop1234", out)

    def test_normal_text_is_untouched(self):
        text = "GET /api/v1/conversations/ 200 in 12ms request_id=7f3a"
        self.assertEqual(triage.redact(text), text)


class ParseTests(unittest.TestCase):
    def test_python_exception_and_app_frame(self):
        err = triage.parse_error(PY)
        self.assertEqual((err.language, err.exc_type), ("python", "TypeError"))
        self.assertIn("offset-naive", err.message)
        self.assertEqual(err.app_frames[-1].func, "is_expired")
        self.assertEqual(err.app_frames[-1].line, 7)
        self.assertIn("expires_at <= now", err.app_frames[-1].code)

    def test_library_frames_are_filtered(self):
        text = ('Traceback (most recent call last):\n'
                '  File "/app/views.py", line 10, in get\n    x = serialize(obj)\n'
                '  File "/usr/lib/python3.12/site-packages/rest_framework/serializers.py", line 5, in data\n    return self.to_rep()\n'
                'AttributeError: \'NoneType\' object has no attribute \'title\'\n')
        err = triage.parse_error(text)
        self.assertEqual([f.file for f in err.app_frames], ["/app/views.py"])
        self.assertEqual(len(err.frames), 2)

    def test_last_traceback_wins(self):
        text = ('Traceback (most recent call last):\n  File "/app/a.py", line 1, in a\n    x\nValueError: first\n\n'
                'Traceback (most recent call last):\n  File "/app/b.py", line 2, in b\n    y\nKeyError: \'second\'\n')
        self.assertEqual(triage.parse_error(text).exc_type, "KeyError")

    def test_node_stack_with_cause(self):
        err = triage.parse_error(NODE)
        self.assertEqual((err.language, err.exc_type, err.message), ("javascript", "Error", "fetch failed"))
        self.assertTrue(err.frames)

    def test_node_library_frames_filtered(self):
        err = triage.parse_error(NODE2)
        self.assertEqual(err.exc_type, "TypeError")
        self.assertEqual(len(err.app_frames), 1)
        self.assertIn("MessageList.tsx", err.app_frames[0].file)

    def test_no_error_found(self):
        self.assertFalse(triage.parse_error("INFO all good\nINFO still fine\n").found)


class ReportTests(unittest.TestCase):
    def report(self, **kw):
        base = dict(symptom="Shared page crashes", expected="Chat is shown", repro=["Open the link"], log_text=PY)
        return triage.build_report(**{**base, **kw})

    def test_has_all_sections(self):
        r = self.report(tried=["restarted docker"])
        for heading in ("## Symptom", "## Expected", "## Steps to reproduce", "## Environment", "## Evidence", "## Already tried"):
            self.assertIn(heading, r)
        self.assertIn("1. Open the link", r)
        self.assertIn("restarted docker", r)

    def test_secrets_never_reach_the_report(self):
        r = self.report()
        self.assertNotIn("abc123def456", r)
        self.assertNotIn("ada@example.com", r)

    def test_points_at_the_app_frame(self):
        self.assertIn("buggy.py:7", self.report())
        self.assertIn("TypeError", self.report())

    def test_missing_parts_are_called_out(self):
        r = self.report(symptom="", repro=[], log_text="")
        self.assertIn("(missing: say what you saw)", r)
        self.assertIn("(missing: how can someone else see it?)", r)
        self.assertIn("No exception found", r)

    def test_long_logs_are_trimmed_to_the_tail(self):
        log = "\n".join(f"line {i}" for i in range(500))
        r = self.report(log_text=log, max_log_lines=10)
        self.assertIn("490 earlier lines omitted", r)
        self.assertIn("line 499", r)
        self.assertNotIn("line 5\n", r)


if __name__ == "__main__":
    unittest.main()
