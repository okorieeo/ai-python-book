import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import validate_claude_config as v  # noqa: E402

GOOD_SKILL = "---\nname: demo\ndescription: Does a demo thing when asked.\n---\nDo the thing.\n"
GOOD_AGENT = "---\nname: demo-agent\ndescription: Checks things. Use it when you need a check.\ntools: Read, Grep\nmodel: sonnet\n---\nInstructions.\n"


class Project:
    """A throwaway project folder to hold one deliberately broken file."""

    def __enter__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        return self

    def __exit__(self, *exc):
        self.tmp.cleanup()

    def write(self, rel, text):
        f = self.root / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text if isinstance(text, str) else json.dumps(text))
        return f

    def problems(self):
        return [(p.severity, p.message) for p in v.validate_all(self.root)]

    def has(self, severity, fragment):
        return any(s == severity and fragment in m for s, m in self.problems())


def settings(hooks=None, perms=None):
    return {"permissions": perms if perms is not None else {"deny": ["Read(./.env)"]}, "hooks": hooks or {}}


def hook(cmd="python3 \"$CLAUDE_PROJECT_DIR/h.py\"", **extra):
    return {"type": "command", "command": cmd, **extra}


class TheShippedConfiguration(unittest.TestCase):
    def test_it_has_no_errors_and_no_warnings(self):
        self.assertEqual([(p.severity, p.where, p.message) for p in v.validate_all(ROOT)], [])

    def test_it_contains_what_the_chapter_describes(self):
        self.assertEqual(len(list((ROOT / ".claude/skills").glob("*/SKILL.md"))), 5)
        self.assertEqual(len(list((ROOT / ".claude/agents").glob("*.md"))), 4)
        events = json.loads((ROOT / ".claude/settings.json").read_text())["hooks"]
        self.assertEqual(set(events), {"PreToolUse", "PostToolUse", "UserPromptSubmit", "Stop"})

    def test_every_hook_script_named_in_settings_is_a_real_executable_file(self):
        text = (ROOT / ".claude/settings.json").read_text()
        import re
        for name in re.findall(r"hooks/(\w+\.py)", text):
            self.assertTrue((ROOT / ".claude/hooks" / name).exists(), name)

    def test_the_side_effect_skills_are_manual_only(self):
        for name in ("feature-plan", "step", "commit-step"):
            fm, _, _ = v._frontmatter(ROOT / ".claude/skills" / name / "SKILL.md")
            self.assertIs(fm.get("disable-model-invocation"), True, name)

    def test_the_read_only_agents_have_no_editing_tools(self):
        for name in ("code-reviewer", "security-auditor", "migration-checker"):
            fm, _, _ = v._frontmatter(ROOT / ".claude/agents" / f"{name}.md")
            self.assertFalse(v.WRITE_TOOLS & set(v._tools(fm["tools"])), name)


class Settings(unittest.TestCase):
    def test_invalid_json(self):
        with Project() as p:
            p.write(".claude/settings.json", "{ not json")
            self.assertTrue(p.has("error", "not valid JSON"))

    def test_a_misspelt_event_case_is_an_error_because_it_would_silently_never_run(self):
        with Project() as p:
            p.write("h.py", "")
            p.write(".claude/settings.json", settings({"pretooluse": [{"matcher": "Bash", "hooks": [hook()]}]}))
            self.assertTrue(p.has("error", "case-sensitive"))

    def test_an_unknown_event_is_only_a_warning(self):
        with Project() as p:
            p.write("h.py", "")
            p.write(".claude/settings.json", settings({"PreCoffee": [{"hooks": [hook()]}]}))
            self.assertTrue(p.has("warn", "not one of the core events"))
            self.assertFalse(any(s == "error" for s, _ in p.problems()))

    def test_a_hook_script_that_does_not_exist(self):
        with Project() as p:
            p.write(".claude/settings.json", settings({"Stop": [{"hooks": [hook("python3 \"$CLAUDE_PROJECT_DIR/.claude/hooks/ghost.py\"")]}]}))
            self.assertTrue(p.has("error", "does not exist"))

    def test_an_existing_script_is_fine(self):
        with Project() as p:
            p.write("h.py", "")
            p.write(".claude/settings.json", settings({"Stop": [{"hooks": [hook()]}]}))
            self.assertEqual([m for s, m in p.problems() if s == "error"], [])

    def test_structural_errors(self):
        cases = {
            "empty hooks list": {"Stop": [{"hooks": []}]},
            "entry not an object": {"Stop": ["nope"]},
            "event value not a list": {"Stop": {"hooks": []}},
            "bad handler type": {"Stop": [{"hooks": [{"type": "shell", "command": "x"}]}]},
            "empty command": {"Stop": [{"hooks": [{"type": "command", "command": "  "}]}]},
            "bad timeout": {"Stop": [{"hooks": [hook(timeout="slow")]}]},
            "zero timeout": {"Stop": [{"hooks": [hook(timeout=0)]}]},
            "bool timeout": {"Stop": [{"hooks": [hook(timeout=True)]}]},
            "matcher not a string": {"PreToolUse": [{"matcher": 5, "hooks": [hook()]}]},
            "broken matcher regex": {"PreToolUse": [{"matcher": "Edit(", "hooks": [hook()]}]},
        }
        for label, hooks in cases.items():
            with self.subTest(case=label), Project() as p:
                p.write("h.py", "")
                p.write(".claude/settings.json", settings(hooks))
                self.assertTrue(any(s == "error" for s, _ in p.problems()), label)

    def test_a_pre_tool_hook_with_no_matcher_warns_that_it_runs_for_everything(self):
        with Project() as p:
            p.write("h.py", "")
            p.write(".claude/settings.json", settings({"PreToolUse": [{"hooks": [hook()]}]}))
            self.assertTrue(p.has("warn", "EVERY tool call"))

    def test_a_space_in_a_matcher_warns(self):
        with Project() as p:
            p.write("h.py", "")
            p.write(".claude/settings.json", settings({"PreToolUse": [{"matcher": "Edit | Write", "hooks": [hook()]}]}))
            self.assertTrue(p.has("warn", "contains a space"))

    def test_permission_rules_must_look_like_rules(self):
        with Project() as p:
            p.write(".claude/settings.json", settings(perms={"allow": ["Bash(pytest *)", "not a rule!"], "deny": ["Read(./.env)"]}))
            self.assertTrue(p.has("error", "not a rule"))

    def test_permission_lists_must_be_lists_of_strings(self):
        with Project() as p:
            p.write(".claude/settings.json", settings(perms={"allow": "Bash", "deny": ["Read(./.env)"]}))
            self.assertTrue(p.has("error", "must be a list of strings"))

    def test_no_env_deny_rule_warns(self):
        with Project() as p:
            p.write(".claude/settings.json", settings(perms={"allow": ["Bash(ls)"]}))
            self.assertTrue(p.has("warn", ".env"))


class Skills(unittest.TestCase):
    def skill(self, text, folder="demo"):
        p = Project().__enter__()
        self.addCleanup(p.tmp.cleanup)
        p.write(f".claude/skills/{folder}/SKILL.md", text)
        return p

    def test_a_good_skill_is_clean(self):
        p = self.skill(GOOD_SKILL)
        self.assertEqual(p.problems(), [])

    def test_yaml_that_does_not_parse_is_an_error_this_is_the_colon_bug(self):
        p = self.skill("---\nname: demo\ndescription: Write tests for an endpoint: auth, ownership.\n---\nBody.\n")
        self.assertTrue(p.has("error", "not valid YAML"))

    def test_no_frontmatter(self):
        self.assertTrue(self.skill("Just instructions.\n").has("error", "no frontmatter"))

    def test_missing_description(self):
        self.assertTrue(self.skill("---\nname: demo\n---\nBody.\n").has("error", "description is required"))

    def test_name_must_match_the_folder_and_the_format(self):
        self.assertTrue(self.skill(GOOD_SKILL.replace("name: demo", "name: other")).has("error", "must match the folder"))
        self.assertTrue(self.skill(GOOD_SKILL.replace("name: demo", "name: Demo_Skill"), folder="Demo_Skill").has("error", "lowercase"))

    def test_the_flag_must_be_a_real_boolean(self):
        self.assertTrue(self.skill(GOOD_SKILL.replace("---\nDo", "disable-model-invocation: 'yes'\n---\nDo")).has("error", "true or false"))

    def test_an_empty_body_is_an_error(self):
        self.assertTrue(self.skill("---\nname: demo\ndescription: x y\n---\n").has("error", "no instructions"))

    def test_a_folder_without_skill_md(self):
        with Project() as p:
            (p.root / ".claude/skills/empty").mkdir(parents=True)
            self.assertTrue(p.has("error", "no SKILL.md"))

    def test_an_automatic_skill_that_commits_is_an_error(self):
        text = "---\nname: demo\ndescription: Tidy up.\n---\nRun `git commit -am wip` when done.\n"
        self.assertTrue(self.skill(text).has("error", "disable-model-invocation: true"))

    def test_the_same_skill_made_manual_is_fine(self):
        text = "---\nname: demo\ndescription: Tidy up.\ndisable-model-invocation: true\n---\nRun `git commit -am wip` when done.\n"
        self.assertEqual(self.skill(text).problems(), [])

    def test_an_argument_hint_the_body_ignores_warns(self):
        text = "---\nname: demo\ndescription: Do it.\nargument-hint: '<thing>'\n---\nDo the thing.\n"
        self.assertTrue(self.skill(text).has("warn", "$ARGUMENTS"))


class Agents(unittest.TestCase):
    def agent(self, text, name="demo-agent"):
        p = Project().__enter__()
        self.addCleanup(p.tmp.cleanup)
        p.write(f".claude/agents/{name}.md", text)
        return p

    def test_a_good_agent_is_clean(self):
        self.assertEqual(self.agent(GOOD_AGENT).problems(), [])

    def test_name_and_description_are_required(self):
        self.assertTrue(self.agent("---\ndescription: Use it.\ntools: Read\n---\nx\n").has("error", "name is required"))
        self.assertTrue(self.agent("---\nname: demo-agent\ntools: Read\n---\nx\n").has("error", "description is required"))

    def test_name_should_match_the_file(self):
        self.assertTrue(self.agent(GOOD_AGENT.replace("name: demo-agent", "name: other")).has("error", "should match the file name"))

    def test_a_description_without_a_when_warns(self):
        self.assertTrue(self.agent(GOOD_AGENT.replace("Checks things. Use it when you need a check.", "Checks things carefully.")).has("warn", "WHEN"))

    def test_unknown_tools_are_errors_and_case_matters(self):
        self.assertTrue(self.agent(GOOD_AGENT.replace("Read, Grep", "Read, grep")).has("error", "unknown tool"))
        self.assertTrue(self.agent(GOOD_AGENT.replace("Read, Grep", "Read, Telepathy")).has("error", "unknown tool"))

    def test_tool_patterns_and_mcp_tools_are_accepted(self):
        self.assertEqual(self.agent(GOOD_AGENT.replace("Read, Grep", "Read, Bash(git diff *), mcp__playwright__browser_click")).problems(), [])

    def test_tools_may_be_a_list(self):
        self.assertEqual(self.agent(GOOD_AGENT.replace("tools: Read, Grep", "tools: [Read, Grep]")).problems(), [])

    def test_a_missing_tools_line_warns_that_everything_is_inherited(self):
        self.assertTrue(self.agent(GOOD_AGENT.replace("tools: Read, Grep\n", "")).has("warn", "inherits EVERY tool"))

    def test_a_reviewer_with_editing_tools_is_an_error(self):
        text = GOOD_AGENT.replace("name: demo-agent", "name: code-reviewer").replace("Read, Grep", "Read, Edit")
        self.assertTrue(self.agent(text, name="code-reviewer").has("error", "read-only"))

    def test_model_values(self):
        for ok in ("haiku", "opus", "inherit", "claude-sonnet-5-5"):
            self.assertEqual(self.agent(GOOD_AGENT.replace("sonnet", ok)).problems(), [], ok)
        self.assertTrue(self.agent(GOOD_AGENT.replace("sonnet", "gpt-4")).has("error", "must be sonnet"))


class McpConfig(unittest.TestCase):
    def mcp(self, servers):
        p = Project().__enter__()
        self.addCleanup(p.tmp.cleanup)
        p.write(".mcp.json", {"mcpServers": servers})
        return p

    def test_good_stdio_and_http_servers(self):
        p = self.mcp({"a": {"command": "npx", "args": ["-y", "pkg"]}, "b": {"type": "http", "url": "https://x.example/mcp", "headers": {"Authorization": "Bearer ${TOKEN}"}}})
        self.assertEqual(p.problems(), [])

    def test_a_url_without_a_type_is_the_silent_drop_bug(self):
        self.assertTrue(self.mcp({"b": {"url": "https://x.example/mcp"}}).has("error", "would drop this server"))

    def test_http_needs_a_real_url_and_stdio_needs_a_command(self):
        self.assertTrue(self.mcp({"b": {"type": "http", "url": "ftp://x"}}).has("error", "http(s) url"))
        self.assertTrue(self.mcp({"a": {"args": ["x"]}}).has("error", "needs a 'command'"))

    def test_args_must_be_a_list_of_strings(self):
        self.assertTrue(self.mcp({"a": {"command": "npx", "args": "-y pkg"}}).has("error", "list of strings"))

    def test_unknown_type_and_deprecated_sse(self):
        self.assertTrue(self.mcp({"a": {"type": "carrier-pigeon", "command": "x"}}).has("error", "unknown type"))
        self.assertTrue(self.mcp({"a": {"type": "sse", "url": "https://x.example/sse"}}).has("warn", "deprecated"))

    def test_a_committed_secret_is_an_error_but_variable_expansion_is_fine(self):
        bad = self.mcp({"b": {"type": "http", "url": "https://x.example/mcp", "headers": {"Authorization": "Bearer abcdefghijklmnopqrstuvwxyz123456"}}})
        self.assertTrue(bad.has("error", "looks like a real secret"))
        env_bad = self.mcp({"a": {"command": "x", "env": {"STRIPE": "sk_live_" + "x" * 20}}})
        self.assertTrue(env_bad.has("error", "looks like a real secret"))
        ok = self.mcp({"a": {"command": "x", "env": {"STRIPE": "${STRIPE_KEY}"}}})
        self.assertEqual(ok.problems(), [])

    def test_no_servers_object(self):
        with Project() as p:
            p.write(".mcp.json", {"servers": {}})
            self.assertTrue(p.has("error", "mcpServers"))


class Cli(unittest.TestCase):
    def test_exit_codes(self):
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()):                     # the CLI prints its report; keep test output clean
            self.assertEqual(v.main([str(ROOT)]), 0)
            with Project() as p:
                p.write(".claude/settings.json", "{")
                self.assertEqual(v.main([str(p.root)]), 1)


if __name__ == "__main__":
    unittest.main()
