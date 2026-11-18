import unittest
from pathlib import Path

from .cases import CaseError, load_cases, parse_lines
from .checks import CHECKS, run_check
from .stats import percentile, wilson_interval


class StatsTests(unittest.TestCase):
    def test_wilson_known_values(self):
        lo, hi = wilson_interval(9, 10)
        self.assertAlmostEqual(lo, 0.596, places=2)
        self.assertAlmostEqual(hi, 0.982, places=2)

    def test_small_samples_are_honestly_wide(self):
        lo, hi = wilson_interval(20, 20)                 # 100% of 20 is NOT "certainly 100%"
        self.assertLess(lo, 0.85)
        self.assertEqual(hi, 1.0)

    def test_more_cases_narrow_the_interval(self):
        w = lambda n: (lambda r: r[1] - r[0])(wilson_interval(int(n * 0.9), n))
        self.assertGreater(w(20), w(100))
        self.assertGreater(w(100), w(400))

    def test_edges(self):
        self.assertEqual(wilson_interval(0, 0), (0.0, 1.0))
        self.assertEqual(wilson_interval(0, 10)[0], 0.0)
        with self.assertRaises(ValueError):
            wilson_interval(11, 10)

    def test_percentile(self):
        self.assertEqual(percentile([], 95), 0.0)
        self.assertEqual(percentile([5], 95), 5.0)
        self.assertEqual(percentile([1, 2, 3, 4], 50), 2.5)
        self.assertEqual(percentile([1, 2, 3, 4, 5], 100), 5.0)
        self.assertEqual(percentile([4, 1, 3, 2], 0), 1.0)
        with self.assertRaises(ValueError):
            percentile([1], 101)


class CheckTests(unittest.TestCase):
    def ok(self, out, t, v=None):
        return run_check(out, t, v).passed

    def test_contains_is_case_insensitive(self):
        self.assertTrue(self.ok("The capital is ABUJA.", "contains", "abuja"))
        self.assertFalse(self.ok("Lagos", "contains", "abuja"))

    def test_contains_any_and_not_contains(self):
        self.assertTrue(self.ok("we cover budgets", "contains_any", ["hiring", "budget"]))
        self.assertFalse(self.ok("hello", "contains_any", ["x", "y"]))
        self.assertFalse(self.ok("As an AI language model, I...", "not_contains", "as an ai language model"))

    def test_regex_and_bad_pattern_is_a_failure_not_a_crash(self):
        self.assertTrue(self.ok("- one\n- two", "regex", r"^\s*[-*]"))
        res = run_check("x", "regex", "([unclosed")
        self.assertFalse(res.passed)
        self.assertIn("invalid pattern", res.detail)

    def test_word_and_char_limits(self):
        self.assertTrue(self.ok("one two three", "max_words", 3))
        self.assertFalse(self.ok("one two three four", "max_words", 3))
        self.assertFalse(self.ok("x" * 11, "max_chars", 10))

    def test_json_checks_including_code_fences(self):
        self.assertTrue(self.ok('{"city": "Kano", "country": "Nigeria"}', "valid_json"))
        self.assertTrue(self.ok('```json\n{"a": 1}\n```', "valid_json"))
        self.assertFalse(self.ok("Sure! {broken", "valid_json"))
        self.assertTrue(self.ok('{"city": "Kano", "country": "NG"}', "json_has_keys", ["city", "country"]))
        res = run_check('{"city": "Kano"}', "json_has_keys", ["city", "country"])
        self.assertFalse(res.passed)
        self.assertIn("country", res.detail)
        self.assertFalse(self.ok("[1, 2]", "json_has_keys", ["a"]))

    def test_no_email(self):
        self.assertTrue(self.ok("I cannot share contact details.", "no_email"))
        self.assertFalse(self.ok("Try ceo@acme.com", "no_email"))

    def test_unknown_check_type_is_an_error(self):
        with self.assertRaises(KeyError):
            run_check("x", "telepathy")


class CaseTests(unittest.TestCase):
    def test_the_shipped_dataset_loads_and_is_well_formed(self):
        cases = load_cases(Path(__file__).parent / "data" / "chat_basic.jsonl")
        self.assertGreaterEqual(len(cases), 12)
        self.assertEqual(len({c.id for c in cases}), len(cases))
        self.assertTrue(all(c.checks or c.rubric for c in cases))
        self.assertTrue({"facts", "format", "safety"} <= {t for c in cases for t in c.tags})

    def test_comments_and_blank_lines_are_ignored(self):
        cases = parse_lines(['# note', '', '{"id":"a","input":"hi","checks":[{"type":"contains","value":"x"}]}'])
        self.assertEqual([c.id for c in cases], ["a"])

    def test_errors_name_the_line(self):
        with self.assertRaisesRegex(CaseError, "line 2: not valid JSON"):
            parse_lines(['{"id":"a","input":"hi","rubric":"r"}', "{oops"])

    def test_duplicate_ids_rejected(self):
        line = '{"id":"a","input":"hi","rubric":"r"}'
        with self.assertRaisesRegex(CaseError, "duplicate id"):
            parse_lines([line, line])

    def test_a_case_that_cannot_fail_is_rejected(self):
        with self.assertRaisesRegex(CaseError, "can never fail"):
            parse_lines(['{"id":"a","input":"hi"}'])

    def test_unknown_check_and_bad_history_rejected(self):
        with self.assertRaisesRegex(CaseError, "unknown check"):
            parse_lines(['{"id":"a","input":"hi","checks":[{"type":"vibes"}]}'])
        with self.assertRaisesRegex(CaseError, "history"):
            parse_lines(['{"id":"a","input":"hi","rubric":"r","history":[["robot","x"]]}'])

    def test_empty_file_rejected(self):
        with self.assertRaises(CaseError):
            parse_lines(["# nothing"])


if __name__ == "__main__":
    unittest.main()
