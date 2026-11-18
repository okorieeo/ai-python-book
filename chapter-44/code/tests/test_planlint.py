import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import planlint  # noqa: E402
from planlint import lint_plan, split_sections  # noqa: E402

STRONG = """# Plan: rename a conversation

## Goal
A signed-in user can rename their own conversation. Nobody else can.

## Files
- `backend/chat/views.py`: add a rename action beside archive
- `backend/chat/serializers.py`: add RenameSerializer
- `backend/chat/tests/test_rename.py` (new): the tests

## Steps
1. Add RenameSerializer with 1 to 80 character validation. Done when: serializer tests pass.
2. Add the PATCH action using OwnedQuerysetMixin. Done when: owner gets 200 in a test.
3. Add the ownership and validation tests. Done when: `pytest backend/chat -q` passes.

## Verification
`pytest backend/chat -q` and `make check`; try it with curl against the dev server.

## Risks and open questions
- The title is shown in the mobile list: do we need to cap the length there too?

## Out of scope
Renaming from the mobile app, which is a separate step.
"""


def repo_with(*paths):
    tmp = tempfile.TemporaryDirectory()
    for p in paths:
        f = Path(tmp.name) / p
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("# stub\n")
    return tmp


class SectionParsing(unittest.TestCase):
    def test_alternative_headings_are_recognised(self):
        text = "## Summary\nx\n## Files to change\n- `a.py`\n## Implementation steps\n1. a\n2. b\n## Test plan\nt\n## Open questions\nq\n## Non-goals\nn\n"
        self.assertEqual(set(split_sections(text)), {"goal", "files", "steps", "verification", "risks", "out_of_scope"})

    def test_formatting_in_headings_is_ignored(self):
        self.assertIn("goal", split_sections("## **Goal:**\nx\n"))

    def test_the_risks_heading_variants_all_match(self):
        for title in ["Risks", "Risks and open questions", "Risks & unknowns", "Open questions", "Unknowns"]:
            with self.subTest(title=title):
                self.assertIn("risks", split_sections(f"## {title}\nbody\n"))
        self.assertNotIn("risks", split_sections("## Risky business\nbody\n"))

    def test_the_first_matching_heading_wins(self):
        self.assertEqual(split_sections("## Goal\nfirst\n## Summary\nsecond\n")["goal"], "first")


class WholePlans(unittest.TestCase):
    def ids(self, text, repo=None):
        return [(f.id, f.severity) for f in lint_plan(text, repo).findings]

    def test_a_good_plan_is_ok_apart_from_the_open_question(self):
        with repo_with("backend/chat/views.py", "backend/chat/serializers.py") as d:
            res = lint_plan(STRONG, d)
        self.assertTrue(res.ok)
        self.assertEqual([f.id for f in res.findings], ["open-questions"])
        self.assertEqual(res.findings[0].severity, "warn")

    def test_a_paragraph_is_not_a_plan(self):
        res = lint_plan("I will add a rename endpoint to the chat app and write some tests for it, then we can see.")
        self.assertFalse(res.ok)
        self.assertEqual({f.id for f in res.findings}, {f"missing-{k}" for k in planlint.SECTIONS})

    def test_an_empty_section_counts_as_missing(self):
        self.assertIn(("missing-out_of_scope", "error"), self.ids(STRONG.replace("Renaming from the mobile app, which is a separate step.", "")))

    def test_a_single_step_is_not_a_plan(self):
        one = STRONG.replace("2. Add the PATCH action using OwnedQuerysetMixin. Done when: owner gets 200 in a test.\n3. Add the ownership and validation tests. Done when: `pytest backend/chat -q` passes.\n", "")
        self.assertIn(("not-a-plan", "error"), self.ids(one))

    def test_thirteen_steps_is_too_big_but_twelve_is_fine(self):
        def many(n):
            steps = "\n".join(f"{i}. Do part {i}. Done when: test {i} passes." for i in range(1, n + 1))
            return STRONG.replace(STRONG[STRONG.index("1. Add RenameSerializer"):STRONG.index("## Verification")], steps + "\n\n")
        self.assertIn(("too-many-steps", "error"), self.ids(many(13)))
        self.assertNotIn("too-many-steps", [i for i, _ in self.ids(many(12))])

    def test_a_step_with_no_way_to_finish_it_is_warned(self):
        text = STRONG.replace("1. Add RenameSerializer with 1 to 80 character validation. Done when: serializer tests pass.", "1. Add RenameSerializer with validation.")
        found = self.ids(text)
        self.assertIn(("step-unverifiable", "warn"), found)
        self.assertEqual(sum(1 for i, _ in found if i == "step-unverifiable"), 1)

    def test_files_that_do_not_exist_are_caught_unless_marked_new(self):
        with repo_with("backend/chat/views.py") as d:                       # serializers.py is missing on disk
            found = [f for f in lint_plan(STRONG, d).findings if f.id == "missing-file"]
        self.assertEqual(len(found), 1)
        self.assertIn("backend/chat/serializers.py", found[0].message)
        self.assertEqual(found[0].severity, "error")

    def test_new_files_are_allowed_to_not_exist(self):
        with repo_with("backend/chat/views.py", "backend/chat/serializers.py") as d:
            self.assertNotIn("missing-file", [f.id for f in lint_plan(STRONG, d).findings])

    def test_without_a_repo_the_existence_check_is_skipped(self):
        self.assertNotIn("missing-file", [i for i, _ in self.ids(STRONG)])

    def test_a_files_section_with_no_paths_is_an_error(self):
        text = STRONG.replace(STRONG[STRONG.index("- `backend/chat/views.py`"):STRONG.index("## Steps")], "Some files in the chat app.\n\n")
        self.assertIn(("files-unlisted", "error"), self.ids(text))

    def test_open_questions_are_counted_and_only_warn(self):
        text = STRONG.replace("## Out of scope", "- Second question?\n\n## Out of scope")
        found = [f for f in lint_plan(text).findings if f.id == "open-questions"]
        self.assertIn("2 open question", found[0].message)

    def test_the_shipped_template_has_every_section(self):
        template = (ROOT / "prompts" / "templates" / "PLAN.template.md").read_text()
        self.assertEqual(set(split_sections(template)), set(planlint.SECTIONS))

    def test_cli_checks_paths_against_the_repo_it_is_given(self):
        with tempfile.TemporaryDirectory() as d, repo_with("backend/chat/views.py", "backend/chat/serializers.py") as repo:
            good, bad = Path(d, "good.md"), Path(d, "bad.md")
            good.write_text(STRONG.replace("?", "."))
            bad.write_text("just do it")
            self.assertEqual(planlint.main([str(good), "--repo", repo]), 0)
            self.assertEqual(planlint.main([str(bad), "--repo", repo]), 1)
            self.assertEqual(planlint.main([str(good), "--repo", d]), 1)      # the same plan against a repo WITHOUT its files fails


if __name__ == "__main__":
    unittest.main()
