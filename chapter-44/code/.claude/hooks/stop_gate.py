#!/usr/bin/env python3
"""
Stop hook: Claude may not finish until your check passes. "I think it works" is not evidence; the check is.
A gate without a ceiling can loop forever on a failure Claude cannot fix, so after STOP_GATE_MAX_BLOCKS consecutive
blocks in one session it lets Claude stop and says plainly that the checks are still failing.
Environment: STOP_CHECK_CMD (default "make check"), STOP_GATE_MAX_BLOCKS (default 3).
"""
from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import read_input  # noqa: E402


def default_runner(command: str, cwd: str) -> tuple[int, str]:
    try:
        r = subprocess.run(shlex.split(command), cwd=cwd, capture_output=True, text=True, timeout=900)
    except FileNotFoundError:
        return 127, f"check command not found: {command}"
    except subprocess.TimeoutExpired:
        return 124, "the check timed out after 15 minutes"
    return r.returncode, r.stdout + r.stderr


def _counter_path(counter_dir: str, session_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", session_id or "unknown")[:80]
    return os.path.join(counter_dir, f"stop-gate-{safe}.count")


def _read(path: str) -> int:
    try:
        with open(path) as fh:
            return int(fh.read().strip() or 0)
    except (OSError, ValueError):
        return 0


def evaluate(data: dict, runner=default_runner, counter_dir: str | None = None, command: str = "make check",
             max_blocks: int = 3, cwd: str | None = None) -> dict | None:
    counter_dir = counter_dir or tempfile.gettempdir()
    path = _counter_path(counter_dir, str(data.get("session_id", "")))
    code, output = runner(command, cwd or data.get("cwd") or os.getcwd())
    if code == 0:
        if os.path.exists(path):
            os.remove(path)
        return None
    blocks = _read(path) + 1
    if blocks > max_blocks:
        if os.path.exists(path):
            os.remove(path)
        return {"systemMessage": f"The stop gate gave up after {max_blocks} attempts: `{command}` is still failing. Review the failures before trusting this work."}
    with open(path, "w") as fh:
        fh.write(str(blocks))
    tail = output.strip()[-2000:]
    return {"decision": "block", "reason": f"`{command}` failed (attempt {blocks} of {max_blocks}). Fix the cause, not the check, then finish.\n\n{tail}"}


def main() -> int:
    data = read_input()
    out = evaluate(data, command=os.environ.get("STOP_CHECK_CMD", "make check"),
                   max_blocks=int(os.environ.get("STOP_GATE_MAX_BLOCKS", 3)), cwd=os.environ.get("CLAUDE_PROJECT_DIR"))
    if out:
        print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
