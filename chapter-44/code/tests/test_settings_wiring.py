"""
Read .claude/settings.json and run its hook commands the way Claude Code would: choose the hooks whose matcher matches
the tool, run each command string through a shell with CLAUDE_PROJECT_DIR set, feed the JSON on stdin, read the result.
This proves the wiring (quoting, variable expansion, matchers, script paths), not just the scripts.
"""
import json
import os
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SETTINGS = json.loads((ROOT / ".claude" / "settings.json").read_text())


def hooks_for(event, tool_name=None):
    commands = []
    for entry in SETTINGS["hooks"].get(event, []):
        matcher = entry.get("matcher")
        if matcher is None or tool_name is None or re.fullmatch(matcher, tool_name):
            commands += [h["command"] for h in entry["hooks"]]
    return commands


def run(command, payload, **env):
    full = {**os.environ, "CLAUDE_PROJECT_DIR": str(ROOT), **env}
    p = subprocess.run(command, shell=True, input=json.dumps(payload), capture_output=True, text=True, cwd=ROOT, env=full, timeout=60)
    return p.returncode, (json.loads(p.stdout) if p.stdout.strip() else None), p.stderr


def pre_bash(command):
    payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(ROOT)}
    results = [run(c, payload) for c in hooks_for("PreToolUse", "Bash")]
    return results


class Matchers(unittest.TestCase):
    def test_the_right_hooks_are_selected_for_each_tool(self):
        self.assertEqual(len(hooks_for("PreToolUse", "Bash")), 2)
        for tool in ("Edit", "Write", "MultiEdit"):
            self.assertEqual(len(hooks_for("PreToolUse", tool)), 1, tool)
            self.assertEqual(len(hooks_for("PostToolUse", tool)), 1, tool)
        for tool in ("Read", "Grep", "Task", "WebFetch"):
            self.assertEqual(hooks_for("PreToolUse", tool), [], tool)

    def test_a_matcher_must_match_the_whole_tool_name(self):
        self.assertIsNone(re.fullmatch("Edit|Write|MultiEdit", "NotebookEdit"))
        self.assertIsNone(re.fullmatch("Bash", "BashOutput"))

    def test_prompt_and_stop_hooks_apply_unconditionally(self):
        self.assertEqual(len(hooks_for("UserPromptSubmit")), 1)
        self.assertEqual(len(hooks_for("Stop")), 1)


class RealCommandsRunThroughAShell(unittest.TestCase):
    def test_a_destructive_command_is_denied_by_the_wired_hook(self):
        results = pre_bash("rm -rf /")
        denies = [out for code, out, _ in results if out and out["hookSpecificOutput"]["permissionDecision"] == "deny"]
        self.assertEqual(len(denies), 1)
        self.assertTrue(all(code == 0 for code, _, _ in results))

    def test_a_harmless_command_passes_every_bash_hook(self):
        self.assertEqual([(c, o) for c, o, _ in pre_bash("pytest -q")], [(0, None), (0, None)])

    def test_a_badly_formatted_commit_is_denied_by_the_second_hook_not_the_first(self):
        (c1, o1, _), (c2, o2, _) = pre_bash('git commit -m "wip"')
        self.assertIsNone(o1)
        self.assertEqual(o2["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_editing_dot_env_is_denied(self):
        payload = {"tool_name": "Write", "tool_input": {"file_path": str(ROOT / ".env")}}
        [(code, out, _)] = [run(c, payload) for c in hooks_for("PreToolUse", "Write")]
        self.assertEqual((code, out["hookSpecificOutput"]["permissionDecision"]), (0, "deny"))

    def test_editing_an_ordinary_file_is_allowed(self):
        payload = {"tool_name": "Edit", "tool_input": {"file_path": str(ROOT / "tools/promptlint.py")}}
        [(code, out, _)] = [run(c, payload) for c in hooks_for("PreToolUse", "Edit")]
        self.assertEqual((code, out), (0, None))

    def test_a_secret_in_a_prompt_blocks_with_exit_2(self):
        fake = "sk_" + "live_" + "Q" * 24
        [(code, out, err)] = [run(c, {"hook_event_name": "UserPromptSubmit", "prompt": f"why does {fake} fail"}) for c in hooks_for("UserPromptSubmit")]
        self.assertEqual(code, 2)
        self.assertIn("Prompt blocked", err)

    def test_the_stop_gate_blocks_on_a_failing_check_and_passes_on_a_good_one(self):
        [cmd] = hooks_for("Stop")
        self.assertEqual(run(cmd, {"session_id": "wire-1"}, STOP_CHECK_CMD="true")[:2], (0, None))
        code, out, _ = run(cmd, {"session_id": "wire-2"}, STOP_CHECK_CMD="false")
        self.assertEqual((code, out["decision"]), (0, "block"))

    def test_the_post_edit_hook_runs_and_stays_quiet_for_a_markdown_file(self):
        payload = {"tool_name": "Edit", "tool_input": {"file_path": str(ROOT / "CLAUDE.md")}}
        [(code, out, _)] = [run(c, payload) for c in hooks_for("PostToolUse", "Edit")]
        self.assertEqual((code, out), (0, None))

    def test_commands_survive_a_project_path_containing_spaces(self):
        import shutil
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            spaced = Path(d) / "my project"
            shutil.copytree(ROOT / ".claude", spaced / ".claude", ignore=shutil.ignore_patterns("__pycache__"))
            payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": "rm -rf /"}}
            p = subprocess.run(hooks_for("PreToolUse", "Bash")[0], shell=True, input=json.dumps(payload), capture_output=True, text=True,
                               env={**os.environ, "CLAUDE_PROJECT_DIR": str(spaced)}, timeout=60)
            self.assertEqual(json.loads(p.stdout)["hookSpecificOutput"]["permissionDecision"], "deny")


if __name__ == "__main__":
    unittest.main()
