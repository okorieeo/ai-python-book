"""Shared plumbing for the hooks. Claude Code runs a hook as a command, sends JSON on stdin, and reads the exit code and stdout."""
from __future__ import annotations

import json
import sys
from typing import Callable


def read_input() -> dict:
    try:
        data = json.load(sys.stdin)
    except (ValueError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def pre_tool_decision(kind: str, reason: str) -> dict:
    """The documented PreToolUse answer: allow, deny, ask or defer, with a reason Claude sees."""
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": kind, "permissionDecisionReason": reason}}


def guard_main(handler: Callable[[dict], int]) -> None:
    """
    Run a SAFETY hook so that it fails CLOSED. Only exit code 2 (or an explicit deny) blocks an action; any other
    non-zero exit is reported but lets the action through. A guard that crashes on odd input must therefore turn
    the crash into a block, or one weird command silently disables the guard.
    """
    try:
        code = handler(read_input())
    except SystemExit:
        raise
    except Exception as exc:                        # noqa: BLE001
        sys.stderr.write(f"guard hook crashed ({type(exc).__name__}: {exc}); blocking to be safe\n")
        sys.exit(2)
    sys.exit(code)
