import unittest

from tools import fix_gate


def diff(path, added=(), removed=()):
    body = "".join(f"-{l}\n" for l in removed) + "".join(f"+{l}\n" for l in added)
    return f"diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n@@ -1,3 +1,3 @@\n{body}"


def levels(text):
    return [(f.level, f.what.split(":")[0]) for f in fix_gate.check(text)]


class FixGateTests(unittest.TestCase):
    def test_clean_fix_with_test_passes(self):
        text = diff("backend/sharing/tokens.py", ["return a <= b"], ["return a < b"]) + \
               diff("backend/sharing/tests/test_tokens.py", ["self.assertTrue(x)"])
        self.assertEqual(fix_gate.check(text), [])

    def test_source_without_test_is_an_error(self):
        out = fix_gate.check(diff("backend/sharing/services.py", ["x = 1"]))
        self.assertEqual(out[0].level, "ERROR")
        self.assertIn("regression test", out[0].what)

    def test_docs_only_change_needs_no_test(self):
        self.assertEqual(fix_gate.check(diff("docs/debug/bug.md", ["notes"])), [])

    def test_web_test_files_are_recognised(self):
        text = diff("web/src/lib/env.ts", ["export const x = 1"]) + diff("web/src/lib/env.test.ts", ["expect(x).toBe(1)"])
        self.assertEqual(fix_gate.check(text), [])

    def test_swallowed_exception(self):
        text = diff("backend/a.py", ["try:", "    run()", "except Exception:", "    pass"]) + diff("backend/tests/test_a.py", ["assert 1"])
        self.assertTrue(any(f.level == "ERROR" and "swallow" in f.what for f in fix_gate.check(text)))

    def test_bare_except_and_empty_catch(self):
        t1 = diff("a.py", ["except:"]) + diff("test_a.py", ["assert 1"])
        t2 = diff("a.ts", ["try { go() } catch (e) {}"]) + diff("a.test.ts", ["expect(1).toBe(1)"])
        self.assertTrue(any(f.level == "ERROR" for f in fix_gate.check(t1)))
        self.assertTrue(any("empty catch" in f.what for f in fix_gate.check(t2)))

    def test_silenced_checks_and_skipped_tests(self):
        src = diff("a.ts", ["// @ts-ignore", "x()"]) + diff("a.test.ts", ["it.skip('x', () => {})"])
        found = [f.what for f in fix_gate.check(src)]
        self.assertTrue(any("check silenced" in w for w in found))
        self.assertTrue(any("test disabled" in w for w in found))

    def test_generated_file_edit(self):
        text = diff("web/src/lib/api/generated/schema.d.ts", ["x"]) + diff("web/a.test.ts", ["expect(1)"])
        self.assertTrue(any("generated file" in f.what for f in fix_gate.check(text)))

    def test_weakened_test_is_a_warning(self):
        text = diff("backend/tests/test_a.py", ["self.assertTrue(x)"], ["self.assertEqual(x, 5)", "self.assertEqual(y, 6)"]) + \
               diff("backend/a.py", ["pass_"])
        self.assertIn(("WARNING", "assertions removed (2 out, 1 in)"), [(f.level, f.what.split(":")[0]) for f in fix_gate.check(text)])

    def test_sleep_and_print_and_dependencies_warn(self):
        text = diff("backend/a.py", ["time.sleep(2)", "print(x)"]) + diff("backend/tests/test_a.py", ["assert 1"]) + diff("web/package.json", ['"left-pad": "1"'])
        found = [f.what for f in fix_gate.check(text) if f.level == "WARNING"]
        self.assertTrue(any("sleep" in w for w in found))
        self.assertTrue(any("debug output" in w for w in found))
        self.assertTrue(any("dependency file" in w for w in found))

    def test_big_diff_warns(self):
        text = diff("a.py", [f"x{i} = {i}" for i in range(350)]) + diff("test_a.py", ["assert 1"])
        self.assertTrue(any("changed lines" in f.what for f in fix_gate.check(text)))

    def test_exit_code(self):
        import io, sys
        for body, expected in ((diff("a.py", ["x = 1"]), 1), (diff("docs/x.md", ["hi"]), 0)):
            old = sys.stdin
            sys.stdin = io.StringIO(body)
            try:
                with __import__("contextlib").redirect_stdout(io.StringIO()):
                    self.assertEqual(fix_gate.main([]), expected)
            finally:
                sys.stdin = old


if __name__ == "__main__":
    unittest.main()
