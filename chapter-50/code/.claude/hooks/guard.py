#!/usr/bin/env python3
"""Claude Code PreToolUse hook: block the few actions that must never happen unattended.

Wire it in .claude/settings.json (see the chapter). Claude Code runs it before every matched tool call and
sends one JSON object on stdin:  {"tool_name": "Bash", "tool_input": {"command": "..."}, ...}
Exit code 2 blocks the call and the message on stderr goes back to Claude. Exit 0 lets the normal
permission flow continue (staying silent does NOT approve anything).

This is DEFENCE IN DEPTH, not a sandbox. A shell is creative: no pattern list can stop everything.
Keep the permission rules in settings.json too, and never give a session credentials it should not use.
"""
from __future__ import annotations

import json
import re
import shlex
import sys

FILE_TOOLS = {"Read", "Edit", "Write", "MultiEdit", "NotebookEdit", "Grep", "Glob"}
PROTECTED_PATH = re.compile(
    r"""(^|/)(
        \.env(\.(?!example$|sample$|template$)[\w.-]+)?     # .env, .env.local, .env.production (not .env.example)
      | .*\.(pem|key|p12|pfx|keystore|jks)
      | id_(rsa|dsa|ecdsa|ed25519)(\.pub)?
      | \.netrc | \.pypirc | \.npmrc | \.git-credentials
      | credentials(\.json)? | secrets?\.(json|ya?ml|toml)
      | terraform\.tfstate(\.backup)? | kubeconfig
    )$""",
    re.VERBOSE | re.IGNORECASE,
)
PROTECTED_DIR = re.compile(r"(^|/)(\.aws|\.ssh|\.gnupg|\.kube|\.docker)(/|$)")
SECRET_NAME = re.compile(r"(?i)(secret|token|passw|api[_-]?key|private|credential|auth)")
SQL_DESTRUCTIVE = re.compile(r"(?i)\b(drop\s+(table|database|schema)|truncate\s+(table\s+)?\w+|delete\s+from\s+\w+\s*;?\s*$)")
PROD_TARGET = re.compile(r"(?i)\b(psql|pg_dump|pg_restore|mysql|mongosh?|redis-cli|ssh|scp|rsync|kubectl|heroku|flyctl)\b.*\b(prod|production|live)\b")
PIPE_TO_SHELL = re.compile(r"(?i)\b(curl|wget)\b[^|]*\|\s*(sudo\s+)?(ba|z|da)?sh\b")


def is_protected_path(path: str) -> bool:
    path = path.strip().strip("\"'").replace("\\", "/")
    return bool(PROTECTED_PATH.search(path) or PROTECTED_DIR.search(path))


def _tokens(command: str) -> list[str]:
    try:
        return shlex.split(command, posix=True)
    except ValueError:
        return command.split()


def _segments(command: str) -> list[list[str]]:
    """Split a command line on ; && || | so each simple command is checked on its own."""
    parts = re.split(r"\s*(?:&&|\|\||;|\|)\s*", command)
    return [t for t in (_tokens(p) for p in parts) if t]


def check_bash(command: str) -> str | None:
    if not command.strip():
        return None
    if PIPE_TO_SHELL.search(command):
        return "Piping a download into a shell is blocked. Download the file, read it, then run it."
    if SQL_DESTRUCTIVE.search(command):
        return "Destructive SQL is blocked. Show me the statement and I will run it myself, on purpose."
    if PROD_TARGET.search(command):
        return "Commands aimed at production are blocked. Ask me to run it and paste redacted output."
    if "dangerously-skip-permissions" in command:
        return "Starting another agent with permissions disabled is blocked."
    for tok in _tokens(command):
        cleaned = tok.lstrip("<>").lstrip("0123456789>")  # 2>.env, >>.env, <.env
        if cleaned and is_protected_path(cleaned):
            return f"'{cleaned}' is a secrets file. Do not read or write it; use .env.example for names only."
    for seg in _segments(command):
        prog, args = seg[0], seg[1:]
        flags = [a for a in args if a.startswith("-")]
        if prog == "sudo":
            return "sudo is blocked in this project."
        if prog in ("env", "printenv"):
            names = [a for a in args if not a.startswith("-") and "=" not in a]
            if prog == "env" and not names and not any("=" in a for a in args):
                return "Dumping the whole environment can expose secrets. Print one variable by name instead."
            if prog == "printenv" and (not names or any(SECRET_NAME.search(n) for n in names)):
                return "Printing the environment or a secret variable is blocked. Print a non-secret variable by name."
        if prog == "rm":
            recursive = any(re.fullmatch(r"-[a-zA-Z]*[rR][a-zA-Z]*", f) or f == "--recursive" for f in flags)
            danger = {"/", "/*", "~", "~/", "$HOME", "*", ".", "..", "./", "./*"}
            if recursive and any(a in danger for a in args if not a.startswith("-")):
                return "Recursive delete of a root, home or whole-directory target is blocked."
        if prog == "chmod" and any(a in ("-R", "--recursive") for a in args) and "777" in args:
            return "chmod -R 777 is blocked."
        if prog == "git":
            sub = next((a for a in args if not a.startswith("-")), "")
            if sub == "push" and (any(f in ("--force", "-f") for f in flags) or any(a in ("main", "master") for a in args)):
                return "Force-pushing, or pushing straight to main, is blocked. Push a branch and open a pull request."
            if sub == "reset" and "--hard" in flags:
                return "git reset --hard discards work. Use git stash, or ask me."
            if sub == "clean" and any(re.fullmatch(r"-[a-z]*f[a-z]*", f) for f in flags):
                return "git clean -f deletes untracked files. Ask me first."
            if "--no-verify" in flags:
                return "Skipping git hooks is blocked."
        if prog == "docker" or (prog == "docker-compose"):
            joined = " ".join(args)
            if re.search(r"\bdown\b.*(\s-v\b|--volumes)", joined) or re.search(r"\b(system|volume|image|builder)\s+prune\b", joined) \
                    or re.search(r"\bvolume\s+rm\b", joined):
                return "This deletes Docker volumes or images (it can delete your database). Ask me to run it."
    return None


def decide(payload: dict) -> tuple[bool, str]:
    """Return (allowed, reason). Pure function: easy to test without Claude Code."""
    tool = payload.get("tool_name", "")
    tool_input = payload.get("tool_input") or {}
    if tool == "Bash":
        reason = check_bash(str(tool_input.get("command", "")))
        return (reason is None, reason or "")
    if tool in FILE_TOOLS:
        for key in ("file_path", "path", "notebook_path"):
            value = tool_input.get(key)
            if isinstance(value, str) and value and is_protected_path(value):
                return False, f"'{value}' is a secrets file and is off limits. Use .env.example for variable names."
    return True, ""


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0  # not our event; never block on a parsing problem
    allowed, reason = decide(payload)
    if not allowed:
        print(f"Blocked by project hook: {reason}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
