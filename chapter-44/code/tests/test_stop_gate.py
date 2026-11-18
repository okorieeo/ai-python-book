import json
import os
import tempfile
import unittest

from hookutil import run_hook

import stop_gate


class Fake:
    def __init__(self, *codes):
        self.codes = list(codes)
        self.calls = 0

    def __call__(self, command, cwd):
        self.calls += 1
        code = self.codes.pop(0) if len(self.codes) > 1 else self.codes[0]
        return code, "FAILED test_x: expected 2 got 3" if code else "ok"


class GateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def ev(self, runner, sid="s1", **kw):
        return stop_gate.evaluate({"session_id": sid}, runner, counter_dir=self.tmp.name, **kw)

    def test_a_passing_check_lets_claude_stop(self):
        self.assertIsNone(self.ev(Fake(0)))

    def test_a_failing_check_blocks_with_the_output(self):
        out = self.ev(Fake(1))
        self.assertEqual(out["decision"], "block")
        self.assertIn("FAILED test_x", out["reason"])
        self.assertIn("attempt 1 of 3", out["reason"])
        self.assertIn("Fix the cause, not the check", out["reason"])

    def test_it_gives_up_after_the_ceiling_and_says_so(self):
        runner = Fake(1)
        results = [self.ev(runner, max_blocks=3) for _ in range(5)]
        self.assertEqual([("decision" in r) for r in results[:3]], [True, True, True])
        self.assertIn("systemMessage", results[3])
        self.assertIn("still failing", results[3]["systemMessage"])
        self.assertIn("decision", results[4])                    # a fresh cycle starts after giving up

    def test_a_pass_resets_the_counter(self):
        runner = Fake(1, 1, 0, 1)
        self.ev(runner); self.ev(runner)
        self.assertIsNone(self.ev(runner))
        self.assertIn("attempt 1 of 3", self.ev(runner)["reason"])

    def test_sessions_do_not_share_counters(self):
        runner = Fake(1)
        self.ev(runner, sid="a"); self.ev(runner, sid="a")
        self.assertIn("attempt 1 of 3", self.ev(runner, sid="b")["reason"])

    def test_hostile_session_ids_cannot_escape_the_counter_folder(self):
        runner = Fake(1)
        self.ev(runner, sid="../../etc/passwd")
        self.assertEqual([os.path.dirname(os.path.join(self.tmp.name, f)) for f in os.listdir(self.tmp.name)], [self.tmp.name])

    def test_a_missing_check_command_is_a_failure_not_a_pass(self):
        out = stop_gate.evaluate({"session_id": "x"}, stop_gate.default_runner, counter_dir=self.tmp.name, command="no-such-command-xyz")
        self.assertEqual(out["decision"], "block")
        self.assertIn("not found", out["reason"])

    def test_long_output_is_trimmed(self):
        runner = lambda command, cwd: (1, "z" * 20_000)
        self.assertLess(len(self.ev(runner)["reason"]), 2_500)


class Protocol(unittest.TestCase):
    def test_exit_zero_and_block_json_through_the_real_script(self):
        with tempfile.TemporaryDirectory() as d:
            ok = run_hook("stop_gate.py", {"session_id": "p1"}, cwd=d, env={"STOP_CHECK_CMD": "true", "TMPDIR": d})
            self.assertEqual(ok[:2], (0, None))
            bad = run_hook("stop_gate.py", {"session_id": "p2"}, cwd=d, env={"STOP_CHECK_CMD": "false", "TMPDIR": d})
            self.assertEqual(bad[0], 0)
            self.assertEqual(bad[1]["decision"], "block")


if __name__ == "__main__":
    unittest.main()
