"""Helpers to run a hook the way Claude Code does: a command, JSON on stdin, exit code and stdout read back."""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOOKS = ROOT / ".claude" / "hooks"
sys.path.insert(0, str(HOOKS))


def run_hook(script: str, payload, *, cwd=None, env=None, raw=None):
    stdin = raw if raw is not None else json.dumps(payload)
    full_env = {**os.environ, **(env or {})}
    full_env.setdefault("CLAUDE_PROJECT_DIR", str(cwd or ROOT))
    proc = subprocess.run([sys.executable, str(HOOKS / script)], input=stdin, capture_output=True, text=True, cwd=cwd or ROOT, env=full_env, timeout=60)
    out = None
    if proc.stdout.strip():
        out = json.loads(proc.stdout)
    return proc.returncode, out, proc.stderr


def bash_payload(command, cwd=None):
    p = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": command}, "session_id": "test"}
    if cwd:
        p["cwd"] = str(cwd)
    return p


def decision_of(out):
    return None if out is None else out["hookSpecificOutput"]["permissionDecision"]
