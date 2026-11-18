#!/usr/bin/env python3
"""
PreToolUse hook for Bash that enforces "one step, one commit": a conventional message, no bypassing hooks, and a
bounded size. A commit that touches thirty files is not a step, it is a pile, and nobody can review a pile.
Limits: MAX_COMMIT_FILES (default 15) and MAX_COMMIT_LINES (default 600) can be set in the environment.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import guard_main, pre_tool_decision  # noqa: E402
from guard_bash import OPERATORS, flags_of, strip_prefixes, tokenize  # noqa: E402

SUBJECT = re.compile(r"^(feat|fix|refactor|test|docs|chore|build|ci|perf|style|revert)(\([\w./-]+\))?!?: \S.*$")


def git_commit_args(command: str) -> list[str] | None:
    """The arguments after `git commit` if the command contains one, else None."""
    try:
        segments = tokenize(command)
    except ValueError:
        return None
    for seg in segments:
        if seg[0] in OPERATORS:
            continue
        toks, _ = strip_prefixes(seg)
        if toks and os.path.basename(toks[0]) == "git":
            rest = toks[1:]
            while rest and rest[0].startswith("-"):
                opt = rest.pop(0)
                if opt in ("-C", "-c") and rest:
                    rest.pop(0)
            if rest and rest[0] == "commit":
                return rest[1:]
    return None


def parse_commit(args: list[str]) -> dict:
    messages, all_flag, no_verify, amend, has_other_message = [], False, False, False, False
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("-m", "--message") and i + 1 < len(args):
            messages.append(args[i + 1]); i += 1
        elif a.startswith("--message="):
            messages.append(a.split("=", 1)[1])
        elif a.startswith("-m") and len(a) > 2 and not a.startswith("--"):
            messages.append(a[2:])
        elif a.startswith("-") and not a.startswith("--") and "m" in a[1:] and i + 1 < len(args):
            messages.append(args[i + 1]); i += 1                          # combined flags such as -am "msg"
            all_flag = all_flag or "a" in a
            no_verify = no_verify or "n" in a[1:a.index("m")]
        elif a in ("-F", "--file", "-C", "-c", "--reuse-message", "--reedit-message") or a.startswith(("--file=", "--reuse-message=")):
            has_other_message = True
        i += 1
    f = flags_of([x for x in args if x.startswith("-")])
    return {"messages": messages, "all": all_flag or bool(f & {"-a", "--all"}), "no_verify": no_verify or bool(f & {"-n", "--no-verify"}),
            "amend": "--amend" in f, "other_message": has_other_message}


def numstat(run_git, use_head: bool) -> tuple[int, int]:
    out = run_git(["diff", "HEAD" if use_head else "--cached", "--numstat"]) or ""
    files = lines = 0
    for row in out.splitlines():
        parts = row.split("\t")
        if len(parts) >= 3:
            files += 1
            for n in parts[:2]:
                lines += int(n) if n.isdigit() else 0                     # binary files show "-"
    return files, lines


def evaluate(command: str, cwd: str, run_git=None, max_files: int = 15, max_lines: int = 600) -> tuple[str | None, str]:
    args = git_commit_args(command)
    if args is None:
        return None, ""
    info = parse_commit(args)
    if info["no_verify"]:
        return "deny", "do not bypass hooks with --no-verify; fix what the hooks reported"
    if not info["messages"] and not info["other_message"] and not info["amend"]:
        return "deny", 'write the message with -m "type(scope): summary" so it can be checked; an editor cannot open here'
    if info["messages"]:
        subject = info["messages"][0].strip().splitlines()[0] if info["messages"][0].strip() else ""
        if not SUBJECT.match(subject):
            return "deny", f'message must look like "feat(chat): rename a conversation" (type, optional scope, colon, summary); got {subject!r}'
        if len(subject) > 72 or subject.endswith("."):
            return "deny", "keep the subject to 72 characters, without a trailing full stop"
    if run_git is None:
        def run_git(argv):
            try:
                r = subprocess.run(["git", *argv], cwd=cwd, capture_output=True, text=True, timeout=30)
            except (OSError, subprocess.SubprocessError):
                return None
            return r.stdout if r.returncode == 0 else None
    files, lines = numstat(run_git, info["all"])
    if files > max_files or lines > max_lines:
        return "deny", (f"this commit changes {files} files and {lines} lines (limits: {max_files} files, {max_lines} lines). "
                        "Split it into smaller commits, one step each, and commit the first now.")
    if info["amend"]:
        return "ask", "amending rewrites the previous commit; confirm it has not been pushed"
    return None, ""


def handle(data: dict) -> int:
    if data.get("tool_name") != "Bash":
        return 0
    command = (data.get("tool_input") or {}).get("command", "")
    cwd = data.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    kind, reason = evaluate(command, cwd, max_files=int(os.environ.get("MAX_COMMIT_FILES", 15)),
                            max_lines=int(os.environ.get("MAX_COMMIT_LINES", 600)))
    if kind:
        print(json.dumps(pre_tool_decision(kind, reason)))
    return 0


if __name__ == "__main__":
    guard_main(handle)
