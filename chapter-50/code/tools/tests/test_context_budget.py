import tempfile
import unittest
from pathlib import Path

from tools import context_budget as cb


def make(tree):
    root = Path(tempfile.mkdtemp())
    for name, size in tree.items():
        p = root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x" * size)
    return root


class BudgetTests(unittest.TestCase):
    def test_tokens_are_chars_over_four(self):
        self.assertEqual(cb.Entry("a.py", 4000).tokens, 1000)

    def test_scan_orders_by_size_and_skips_vendor_folders(self):
        root = make({"src/a.py": 400, "src/big.py": 40000, "node_modules/x/y.js": 99999, ".git/c.txt": 5000, "logo.png": 100})
        got = cb.scan(root)
        self.assertEqual([e.path for e in got], ["src/big.py", "src/a.py"])

    def test_noisy_classification(self):
        for path, label in (("package-lock.json", "lockfile"), ("web/pnpm-lock.yaml", "lockfile"), ("static/app.min.js", "minified or map"),
                            ("web/src/lib/api/generated/schema.d.ts", "generated code"), ("logs/app.log", "log or dump"), ("src/main.py", "")):
            self.assertEqual(cb.classify(path), label, path)

    def test_deny_rules_only_for_big_noisy_files(self):
        root = make({"package-lock.json": 40000, "tiny.log": 100, "src/app.py": 80000})
        self.assertEqual(cb.deny_rules(cb.scan(root)), ['"Read(./package-lock.json)"'])


if __name__ == "__main__":
    unittest.main()
