"""Run: python -m unittest tools.test_lint_claude_config -v"""
import json
import tempfile
import unittest
from pathlib import Path

from tools import lint_claude_config as lc

GOOD_MD = """# App
Short description.

## Commands
- Tests: `python -m pytest -q`
- Lint: `ruff check .`

## Rules
- Money is an integer in minor units.
"""


def codes(findings):
    return {f.code for f in findings}


class ClaudeMdTests(unittest.TestCase):
    def test_good_file_is_clean(self):
        self.assertEqual(lc.lint_claude_md(GOOD_MD), [])

    def test_empty(self):
        self.assertEqual(codes(lc.lint_claude_md("  \n")), {"empty"})

    def test_length_thresholds(self):
        long = GOOD_MD + "\n".join(f"- rule number {i} is here" for i in range(210))
        self.assertIn("long", codes(lc.lint_claude_md(long)))
        huge = GOOD_MD + "\n".join(f"- rule number {i} is here" for i in range(420))
        self.assertIn("too-long", codes(lc.lint_claude_md(huge)))

    def test_vague_instructions_flagged(self):
        r = lc.lint_claude_md(GOOD_MD + "\n- Write clean code and follow best practices.\n")
        self.assertEqual([f.code for f in r].count("vague"), 2)

    def test_vague_phrase_inside_code_block_is_ignored(self):
        text = GOOD_MD + "\n```\nwrite clean code\n```\n"
        self.assertNotIn("vague", codes(lc.lint_claude_md(text)))

    def test_html_comments_are_ignored(self):
        text = GOOD_MD + "\n<!-- maintainer: be careful here -->\n"
        self.assertNotIn("vague", codes(lc.lint_claude_md(text)))

    def test_secrets_detected(self):
        for secret in ("key sk_live_ABCDEFGH12345678", "ANTHROPIC sk-ant-abcdefgh12345678", "id AKIAABCDEFGHIJKLMNOP",
                       "password = hunter22222", "-----BEGIN RSA PRIVATE KEY-----"):
            with self.subTest(secret=secret):
                self.assertIn("secret", codes(lc.lint_claude_md(GOOD_MD + "\n" + secret + "\n")))

    def test_placeholders_are_not_secrets(self):
        text = GOOD_MD + "\n- Set the token with `$TOKEN` from the environment.\n"
        self.assertNotIn("secret", codes(lc.lint_claude_md(text)))

    def test_personal_paths(self):
        self.assertIn("personal-path", codes(lc.lint_claude_md(GOOD_MD + "\n- Docs at /Users/amina/work/docs\n")))
        self.assertIn("personal-path", codes(lc.lint_claude_md(GOOD_MD + "\n- Docs at C:\\Users\\amina\\docs\n")))

    def test_no_commands(self):
        self.assertIn("no-commands", codes(lc.lint_claude_md("# App\n\nA chat app.\n")))

    def test_commands_without_tests(self):
        r = lc.lint_claude_md("# App\n- Start: `docker compose up -d`\n")
        self.assertEqual(codes(r), {"no-test-command"})

    def test_cd_prefixed_test_command_counts(self):
        self.assertEqual(lc.lint_claude_md("# App\n- Test: `cd backend && python -m pytest -q`\n"), [])

    def test_duplicates(self):
        text = GOOD_MD + "\n- Never log message text or personal data anywhere\n- Never log message text or personal data anywhere\n"
        self.assertIn("duplicate", codes(lc.lint_claude_md(text)))

    def test_imports(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            (base / "docs").mkdir()
            (base / "docs" / "git.md").write_text("x")
            ok = lc.lint_claude_md(GOOD_MD + "\nSee @docs/git.md\n", base_dir=base)
            bad = lc.lint_claude_md(GOOD_MD + "\nSee @docs/missing.md\n", base_dir=base)
            literal = lc.lint_claude_md(GOOD_MD + "\nMention `@docs/missing.md` literally\n", base_dir=base)
        self.assertEqual(ok, [])
        self.assertEqual(codes(bad), {"missing-import"})
        self.assertEqual(literal, [])


def settings(**perms):
    return json.dumps({"permissions": perms})


GOOD_DENY = ["Read(./.env)", "Bash(git push *)"]


class SettingsTests(unittest.TestCase):
    def test_good_settings(self):
        self.assertEqual(lc.lint_settings(settings(allow=["Bash(npm run test *)", "Bash(git diff *)"], deny=GOOD_DENY)), [])

    def test_invalid_json(self):
        self.assertEqual(codes(lc.lint_settings("{ nope")), {"invalid-json"})
        self.assertEqual(codes(lc.lint_settings("[]")), {"invalid-json"})

    def test_allow_all_shell(self):
        for rule in ("Bash", "Bash(*)", "PowerShell(*)"):
            self.assertIn("allow-all-shell", codes(lc.lint_settings(settings(allow=[rule], deny=GOOD_DENY))))

    def test_interpreter_wildcards(self):
        for rule in ("Bash(python*)", "Bash(python *)", "Bash(node *)"):
            with self.subTest(rule=rule):
                self.assertIn("allow-interpreter", codes(lc.lint_settings(settings(allow=[rule], deny=GOOD_DENY))))

    def test_specific_python_command_is_fine(self):
        self.assertEqual(lc.lint_settings(settings(allow=["Bash(python -m pytest *)"], deny=GOOD_DENY)), [])

    def test_dangerous_allows(self):
        for rule in ("Bash(rm -rf build)", "Bash(sudo apt install *)"):
            self.assertIn("allow-dangerous", codes(lc.lint_settings(settings(allow=[rule], deny=GOOD_DENY))))

    def test_wildcard_before_subcommand(self):
        self.assertIn("wildcard-before-subcommand", codes(lc.lint_settings(settings(allow=["Bash(git * main)"], deny=GOOD_DENY))))

    def test_rules_that_never_match(self):
        for rule in ("Write(docs/**)", "Glob(src/**)", "NotebookEdit(a.ipynb)"):
            self.assertIn("never-matches", codes(lc.lint_settings(settings(allow=[rule], deny=GOOD_DENY))))

    def test_single_slash_absolute_path(self):
        self.assertIn("single-slash-path", codes(lc.lint_settings(settings(deny=GOOD_DENY + ["Read(/Users/amina/secrets/**)"]))))
        self.assertNotIn("single-slash-path", codes(lc.lint_settings(settings(deny=GOOD_DENY + ["Read(//Users/amina/secrets/**)"]))))
        self.assertNotIn("single-slash-path", codes(lc.lint_settings(settings(deny=GOOD_DENY + ["Edit(/src/**)"]))))

    def test_env_not_denied(self):
        self.assertIn("env-not-denied", codes(lc.lint_settings(settings(deny=["Bash(git push *)"]))))
        for rule in ("Read(./.env)", "Read(**/.env)", "Read(.env)", "Read(./.env.*)"):
            self.assertNotIn("env-not-denied", codes(lc.lint_settings(settings(deny=[rule, "Bash(git push *)"]))))

    def test_push_gate_is_a_note(self):
        r = lc.lint_settings(settings(deny=["Read(./.env)"]))
        self.assertEqual([(f.level, f.code) for f in r], [("info", "push-not-gated")])
        self.assertEqual(lc.lint_settings(settings(ask=["Bash(git push *)"], deny=["Read(./.env)"])), [])

    def test_default_mode_rules(self):
        self.assertIn("bypass-in-project", codes(lc.lint_settings(settings(defaultMode="bypassPermissions", deny=GOOD_DENY))))
        self.assertIn("auto-in-project", codes(lc.lint_settings(settings(defaultMode="auto", deny=GOOD_DENY))))
        self.assertEqual(lc.lint_settings(settings(defaultMode="plan", deny=GOOD_DENY)), [])
        self.assertNotIn("auto-in-project", codes(lc.lint_settings(settings(defaultMode="auto", deny=GOOD_DENY), scope="user")))
        self.assertIn("unknown-mode", codes(lc.lint_settings(settings(defaultMode="yolo", deny=GOOD_DENY))))

    def test_secret_in_env_block(self):
        text = json.dumps({"permissions": {"deny": GOOD_DENY}, "env": {"STRIPE_KEY": "sk_live_ABCDEFGH12345678"}})
        self.assertIn("secret", codes(lc.lint_settings(text)))


class ProjectTests(unittest.TestCase):
    def make(self, **files):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        root = Path(d.name)
        for name, content in files.items():
            path = root / name.replace("__", "/")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        return root

    def test_missing_claude_md(self):
        root = self.make()
        self.assertEqual([f.code for _, f in lc.lint_project(root)], ["missing"])

    def test_clean_project(self):
        root = self.make(**{"CLAUDE.md": GOOD_MD, ".claude__settings.json": settings(deny=GOOD_DENY)})
        self.assertEqual(lc.lint_project(root), [])

    def test_personal_files_must_be_ignored(self):
        root = self.make(**{"CLAUDE.md": GOOD_MD, "CLAUDE.local.md": "mine", ".gitignore": "node_modules\n"})
        self.assertIn("personal-file-tracked", {f.code for _, f in lc.lint_project(root)})
        (root / ".gitignore").write_text("CLAUDE.local.md\n")
        self.assertNotIn("personal-file-tracked", {f.code for _, f in lc.lint_project(root)})

    def test_rule_files_are_checked(self):
        root = self.make(**{"CLAUDE.md": GOOD_MD, ".claude__rules__x.md": "key sk_live_ABCDEFGH12345678\n"})
        self.assertIn("secret", {f.code for _, f in lc.lint_project(root)})

    def test_starter_kit_is_clean(self):
        starter = Path(__file__).resolve().parent.parent / "claude_starter"
        self.assertEqual(lc.lint_project(starter), [])

    def test_cli_exit_codes(self):
        bad = self.make(**{"CLAUDE.md": GOOD_MD + "\nkey sk_live_ABCDEFGH12345678\n"})
        good = self.make(**{"CLAUDE.md": GOOD_MD})
        self.assertEqual(lc.main([str(bad)]), 1)
        self.assertEqual(lc.main([str(good)]), 0)


if __name__ == "__main__":
    unittest.main()
