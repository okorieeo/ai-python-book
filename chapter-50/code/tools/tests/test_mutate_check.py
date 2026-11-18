import tempfile
import unittest
from pathlib import Path

from tools import mutate_check as mc

SRC = "def f(a, b):\n    if a > b and a != 0:\n        return a + 1\n    return not b\n"


class MutantTests(unittest.TestCase):
    def test_finds_the_expected_mutants(self):
        kinds = [m.description for m in mc.list_mutants(SRC)]
        for expected in ("Gt -> GtE", "NotEq -> Eq", "And -> Or", "Add -> Sub", "0 -> 1", "1 -> 2", "removed 'not'"):
            self.assertIn(expected, kinds)

    def test_applying_changes_exactly_one_thing(self):
        for m in mc.list_mutants(SRC):
            new = mc.apply_mutant(SRC, m.index)
            self.assertNotEqual(new.strip(), SRC.strip())
            compile(new, "<mutant>", "exec")  # always valid Python
        gt = next(m for m in mc.list_mutants(SRC) if m.description == "Gt -> GtE")
        self.assertIn("a >= b", mc.apply_mutant(SRC, gt.index))
        removed = next(m for m in mc.list_mutants(SRC) if "not" in m.description)
        self.assertIn("return b", mc.apply_mutant(SRC, removed.index))

    def test_line_range_limits_mutants(self):
        self.assertTrue(all(m.lineno == 3 for m in mc.list_mutants(SRC, (3, 3))))

    def test_strings_are_not_mutated(self):
        self.assertEqual(mc.list_mutants('x = "hello"\n'), [])


class RunTests(unittest.TestCase):
    def project(self, test_body):
        d = tempfile.mkdtemp()
        root = Path(d)
        (root / "pkg").mkdir()
        (root / "pkg" / "__init__.py").write_text("")
        (root / "pkg" / "m.py").write_text("def older(age):\n    return age > 17\n")
        (root / "pkg" / "test_m.py").write_text("import unittest\nfrom pkg import m\nclass T(unittest.TestCase):\n" + test_body)
        return root

    def test_weak_tests_let_a_mutant_survive_and_strong_tests_kill_all(self):
        weak = self.project("    def test_a(self):\n        self.assertTrue(m.older(30))\n")
        killed, survived = mc.mutation_test(weak, "pkg/m.py", "pkg.test_m")
        self.assertTrue(survived)
        strong = self.project("    def test_a(self):\n        self.assertTrue(m.older(18))\n        self.assertFalse(m.older(17))\n        self.assertTrue(m.older(30))\n")
        killed, survived = mc.mutation_test(strong, "pkg/m.py", "pkg.test_m")
        self.assertEqual(survived, [])
        self.assertTrue(killed)

    def test_original_file_is_never_modified(self):
        root = self.project("    def test_a(self):\n        self.assertTrue(m.older(30))\n")
        before = (root / "pkg" / "m.py").read_text()
        mc.mutation_test(root, "pkg/m.py", "pkg.test_m")
        self.assertEqual((root / "pkg" / "m.py").read_text(), before)

    def test_refuses_when_tests_fail_on_the_original(self):
        root = self.project("    def test_a(self):\n        self.assertTrue(m.older(1))\n")
        with self.assertRaises(RuntimeError):
            mc.mutation_test(root, "pkg/m.py", "pkg.test_m")


if __name__ == "__main__":
    unittest.main()
