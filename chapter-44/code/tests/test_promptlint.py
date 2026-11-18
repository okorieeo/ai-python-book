import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import promptlint  # noqa: E402
from promptlint import lint  # noqa: E402

PAIRS = ROOT / "prompts" / "weak_vs_strong"
GOOD = """Add a /health endpoint to the Django API.

Context: follow the pattern of the existing status view in @backend/core/views.py.
Constraints: do not add a dependency; only check the database, never an external service.
Done when: a test in backend/core/tests/test_health.py shows it returns 200, and `make check` passes."""


class ThePairs(unittest.TestCase):
    def test_every_weak_prompt_fails(self):
        files = sorted(PAIRS.glob("*-weak.md"))
        self.assertEqual(len(files), 9)
        for f in files:
            with self.subTest(prompt=f.name):
                self.assertFalse(lint(f.read_text()).ok, f.name)

    def test_every_strong_prompt_passes_with_no_errors_and_all_four_parts(self):
        files = sorted(PAIRS.glob("*-strong.md"))
        self.assertEqual(len(files), 9)
        for f in files:
            res = lint(f.read_text())
            with self.subTest(prompt=f.name):
                self.assertEqual(res.score, 4, f.name)
                self.assertTrue(res.ok, [x.id for x in res.findings])

    def test_each_weak_prompt_is_missing_at_least_two_of_the_four_parts(self):
        for f in PAIRS.glob("*-weak.md"):
            self.assertLessEqual(lint(f.read_text()).score, 2, f.name)

    def test_every_strong_prompt_is_a_better_version_of_a_weak_one(self):
        for weak in PAIRS.glob("*-weak.md"):
            strong = weak.with_name(weak.name.replace("-weak", "-strong"))
            self.assertTrue(strong.exists(), weak.name)
            self.assertGreater(lint(strong.read_text()).score, lint(weak.read_text()).score)

    def test_the_templates_pass_their_own_checklist(self):
        for f in (ROOT / "prompts" / "templates").glob("*.md"):
            if f.name.startswith("PLAN"):
                continue
            with self.subTest(template=f.name):
                self.assertTrue(lint(f.read_text()).ok, [(x.id) for x in lint(f.read_text()).findings])


class Elements(unittest.TestCase):
    def ids(self, text):
        return {f.id for f in lint(text).findings}

    def test_a_good_prompt_passes_cleanly(self):
        res = lint(GOOD)
        self.assertTrue(res.ok)
        self.assertEqual([f for f in res.findings if f.severity == "error"], [])

    def test_missing_each_part_is_reported_by_name(self):
        no_context = "Add a health endpoint to the API. Constraints: do not add a dependency. Done when: a test returns 200 and `make check` passes."
        self.assertEqual(self.ids(no_context) & {"no-context"}, {"no-context"})
        no_constraints = "Add a health endpoint to @backend/core/views.py for the monitoring system. Done when: a test returns 200 and `make check` passes."
        self.assertIn("no-constraints", self.ids(no_constraints))
        no_accept = "Add a health endpoint to @backend/core/views.py for the monitoring system. Do not add a dependency and keep it small and boring."
        self.assertIn("no-acceptance", self.ids(no_accept))
        no_goal = "The health endpoint in @backend/core/views.py is missing. Do not add a dependency. Done when: a test returns 200."
        self.assertIn("no-goal", self.ids(no_goal))

    def test_too_short_is_an_error_even_if_it_starts_with_a_verb(self):
        res = lint("Add a login page")
        self.assertIn("too-short", {f.id for f in res.findings})
        self.assertFalse(res.ok)

    def test_empty_input_fails_without_crashing(self):
        self.assertFalse(lint("").ok)
        self.assertFalse(lint("   \n\n").ok)

    def test_word_boundaries_stop_false_matches(self):
        sentence = "Add the latest greatest contest page in backend/core/views.py and keep protest data. Do not touch other files."
        self.assertIn("no-acceptance", self.ids(sentence))          # 'latest', 'contest' and 'protest' are not 'test'

    def test_a_done_when_label_alone_counts_as_acceptance(self):
        self.assertTrue(lint(GOOD.replace("a test in backend/core/tests/test_health.py shows it returns 200, and `make check` passes", "the endpoint answers")).elements["acceptance"])

    def test_two_distinct_cues_count_without_a_label(self):
        text = "Add a /health route in @backend/core/views.py. Do not add dependencies. It must return 200 and the tests should pass."
        self.assertTrue(lint(text).elements["acceptance"])

    def test_paths_urls_and_bare_filenames_all_count_as_context(self):
        for ctx in ["see @web/lib/format.ts", "see https://docs.expo.dev/versions/latest/sdk/notifications/", "see settings.py for the flag", "see backend/chat/views.py"]:
            with self.subTest(ctx=ctx):
                self.assertTrue(lint(f"Add a flag to the app, {ctx}. Do not break it. Done when the tests pass.").elements["context"])

    def test_html_comments_in_a_template_are_ignored(self):
        text = "<!-- write this for the reader -->\n[Goal] Add a flag in @core/flags.py. Do not add deps. Done when: a test covers it."
        self.assertTrue(lint(text).elements["goal"])


class Habits(unittest.TestCase):
    def test_vague_words_warn_unless_the_sentence_has_a_number(self):
        vague = GOOD + "\nAlso make it better and cleaner."
        self.assertIn("vague-word", {f.id for f in lint(vague).findings})
        measured = GOOD + "\nKeep the response faster than 200 ms."
        self.assertNotIn("vague-word", {f.id for f in lint(measured).findings})

    def test_vague_words_are_warnings_not_errors(self):
        res = lint(GOOD + "\nMake it nicer.")
        self.assertTrue(res.ok)
        self.assertEqual({f.severity for f in res.findings if f.id == "vague-word"}, {"warn"})

    def test_a_list_of_many_tasks_warns_to_split(self):
        tasks = "\n".join(f"{i}. Add feature number {i} to @app/file{i}.py" for i in range(1, 9))
        res = lint("Add these features. Do not break anything. Done when tests pass.\n" + tasks)
        self.assertIn("too-big", {f.id for f in res.findings})

    def test_a_short_list_does_not_warn(self):
        self.assertNotIn("too-big", {f.id for f in lint(GOOD + "\n- one\n- two\n- three").findings})

    def test_the_constraints_list_itself_is_not_counted_as_many_tasks(self):
        long_constraints = GOOD + "\nMore constraints:\n" + "\n".join(f"- Do not change module {i}" for i in range(9))
        self.assertNotIn("too-big", {f.id for f in lint(long_constraints).findings})
        long_checks = GOOD + "\nDone when:\n" + "\n".join(f"- Only the owner may rename chat {i}" for i in range(9))
        self.assertNotIn("too-big", {f.id for f in lint(long_checks).findings})

    def test_huge_prompts_warn(self):
        self.assertIn("too-big", {f.id for f in lint(GOOD + " " + "word " * 450).findings})

    def test_cli_exit_code_reflects_failures(self):
        self.assertEqual(promptlint.main([str(PAIRS / "backend-01-strong.md")]), 0)
        self.assertEqual(promptlint.main([str(PAIRS / "backend-01-weak.md")]), 1)


if __name__ == "__main__":
    unittest.main()
