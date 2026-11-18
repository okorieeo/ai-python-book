import unittest

from hookutil import run_hook

import post_edit_check as pec


def runner(results):
    """results: argv[0..1] joined -> (returncode, output). Anything unlisted succeeds."""
    calls = []

    def run(argv, cwd):
        calls.append(argv)
        for key, value in results.items():
            if " ".join(argv).startswith(key):
                return value
        return 0, ""
    run.calls = calls
    return run


class PlanTests(unittest.TestCase):
    def test_python_gets_ruff(self):
        self.assertEqual([k for k, _ in pec.plan_checks("a/b.py")], ["format", "check"])
        self.assertEqual(pec.plan_checks("a/b.py")[1][1][:2], ["ruff", "check"])

    def test_javascript_family_gets_prettier_and_eslint(self):
        for p in ["x.ts", "x.tsx", "x.js", "x.jsx", "x.mjs"]:
            self.assertEqual(pec.plan_checks(p)[0][1][:4], ["npx", "--no-install", "prettier", "--write"], p)

    def test_other_files_get_nothing(self):
        for p in ["README.md", "data.json", "image.png", "Makefile", "noextension"]:
            self.assertEqual(pec.plan_checks(p), [], p)

    def test_the_extension_check_is_case_insensitive(self):
        self.assertTrue(pec.plan_checks("OLD.PY"))


class EvaluateTests(unittest.TestCase):
    def test_clean_edit_says_nothing(self):
        self.assertIsNone(pec.evaluate("a.py", ".", runner({})))

    def test_a_lint_failure_blocks_and_shows_claude_the_output(self):
        out = pec.evaluate("a.py", ".", runner({"ruff check": (1, "a.py:3:1: F401 unused import os")}))
        self.assertEqual(out["decision"], "block")
        self.assertIn("F401 unused import", out["reason"])
        self.assertIn("ruff check a.py", out["reason"])

    def test_a_formatter_failure_never_blocks(self):
        self.assertIsNone(pec.evaluate("a.py", ".", runner({"ruff format": (1, "boom")})))

    def test_a_missing_tool_is_skipped_quietly(self):
        self.assertIsNone(pec.evaluate("a.py", ".", runner({"ruff": (127, "")})))

    def test_long_output_is_trimmed(self):
        out = pec.evaluate("a.py", ".", runner({"ruff check": (1, "e" * 10_000)}))
        self.assertLess(len(out["reason"]), 2_000)

    def test_both_failures_are_reported_for_js(self):
        out = pec.evaluate("a.ts", ".", runner({"npx --no-install eslint": (1, "no-unused-vars")}))
        self.assertIn("no-unused-vars", out["reason"])

    def test_changing_models_py_reminds_about_migrations(self):
        out = pec.evaluate("backend/chat/models.py", ".", runner({}))
        self.assertEqual(out["hookSpecificOutput"]["hookEventName"], "PostToolUse")
        self.assertIn("makemigrations --check", out["hookSpecificOutput"]["additionalContext"])
        self.assertNotIn("decision", out)

    def test_unrelated_file_types_do_nothing_at_all(self):
        self.assertIsNone(pec.evaluate("README.md", ".", runner({})))


class Protocol(unittest.TestCase):
    def test_non_edit_tools_are_ignored(self):
        code, out, _ = run_hook("post_edit_check.py", {"tool_name": "Bash", "tool_input": {"command": "ls"}})
        self.assertEqual((code, out), (0, None))

    def test_a_models_py_edit_returns_the_context_json(self):
        code, out, _ = run_hook("post_edit_check.py", {"tool_name": "Edit", "tool_input": {"file_path": "backend/chat/models.py"}})
        self.assertEqual(code, 0)
        self.assertIn("additionalContext", out["hookSpecificOutput"])

    def test_garbage_input_never_blocks_an_edit(self):
        self.assertEqual(run_hook("post_edit_check.py", None, raw="{{{")[0], 0)


if __name__ == "__main__":
    unittest.main()
