#!/usr/bin/env python3
"""
PostToolUse hook for Edit and Write: after Claude changes a file, format it and lint it, and put any complaint
straight back in front of Claude so it fixes the problem in the same turn. Missing tools are skipped, not errors.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import read_input  # noqa: E402

JS_EXT = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}


def plan_checks(path: str) -> list[tuple[str, list[str]]]:
    """(kind, argv) pairs. 'format' commands rewrite the file and never block; 'check' commands can."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".py":
        return [("format", ["ruff", "format", path]), ("check", ["ruff", "check", path])]
    if ext in JS_EXT:
        return [("format", ["npx", "--no-install", "prettier", "--write", path]), ("check", ["npx", "--no-install", "eslint", path])]
    return []


def default_runner(argv: list[str], cwd: str) -> tuple[int, str]:
    try:
        r = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=120)
    except FileNotFoundError:
        return 127, ""
    except subprocess.TimeoutExpired:
        return 124, "timed out"
    return r.returncode, (r.stdout + r.stderr)


def evaluate(path: str, cwd: str, runner=default_runner) -> dict | None:
    problems: list[str] = []
    for kind, argv in plan_checks(path):
        code, output = runner(argv, cwd)
        if code == 127:
            continue                                    # the tool is not installed here: skip, do not nag
        if kind == "check" and code != 0:
            problems.append(f"$ {' '.join(argv)}\n{output.strip()[-1500:]}")
    result: dict = {}
    if problems:
        result["decision"] = "block"
        result["reason"] = "The edit left problems. Fix them before continuing:\n\n" + "\n\n".join(problems)
    if path.replace("\\", "/").endswith("/models.py"):
        result["hookSpecificOutput"] = {
            "hookEventName": "PostToolUse",
            "additionalContext": "models.py changed: run `python manage.py makemigrations --check --dry-run`; if it reports changes, create the migration in this step.",
        }
    return result or None


def main() -> int:
    data = read_input()
    if data.get("tool_name") not in ("Edit", "Write", "MultiEdit"):
        return 0
    path = (data.get("tool_input") or {}).get("file_path", "")
    cwd = os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or os.getcwd()
    out = evaluate(path, cwd) if path else None
    if out:
        print(json.dumps(out))
    return 0            # advisory: a crash here must NOT block the edit, so no fail-closed wrapper


if __name__ == "__main__":
    sys.exit(main())
