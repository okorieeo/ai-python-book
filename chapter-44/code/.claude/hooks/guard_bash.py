#!/usr/bin/env python3
"""
PreToolUse hook for Bash. Denies the commands you never want an agent to run, and asks about the ones that are
sometimes legitimate but always deserve a human look. CLAUDE.md can ask Claude to be careful; this makes it so.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import guard_main, pre_tool_decision  # noqa: E402

SAFE_RM_TARGETS = {"node_modules", ".next", "dist", "build", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
                   "coverage", ".turbo", ".expo"}
PREFIXES = {"sudo", "command", "nohup", "time", "env", "exec", "nice"}
SHELLS = {"sh", "bash", "zsh", "dash"}
ENV_FILE = re.compile(r"(^|/)\.env(\.(?!example$|sample$|template$)[\w.-]+)?$", re.IGNORECASE)
OPERATORS = {"&&", "||", ";", "|", "&", "\n"}


def tokenize(command: str) -> list[list[str]]:
    """Split a command line into segments of tokens, keeping the operator that came before each segment."""
    lex = shlex.shlex(command, posix=True, punctuation_chars=True)
    lex.whitespace_split = True
    lex.commenters = ""
    segments: list[list[str]] = [[]]
    for tok in lex:
        if tok in OPERATORS:
            segments.append([tok])
            segments.append([])
        else:
            segments[-1].append(tok)
    return [s for s in segments if s]


def strip_prefixes(tokens: list[str]) -> tuple[list[str], bool]:
    used_sudo = False
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", t):
            i += 1
        elif t in PREFIXES:
            used_sudo = used_sudo or t == "sudo"
            i += 1
        else:
            break
    return tokens[i:], used_sudo


def env_assignments(tokens: list[str]) -> dict[str, str]:
    out = {}
    for t in tokens:
        m = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)=(.*)", t)
        if not m:
            break
        out[m.group(1)] = m.group(2)
    return out


def flags_of(args: list[str]) -> set[str]:
    flags: set[str] = set()
    for a in args:
        if a.startswith("--"):
            flags.add(a.split("=", 1)[0])
        elif a.startswith("-") and len(a) > 1 and not a[1].isdigit():
            flags.update("-" + c for c in a[1:])
    return flags


def rank(kind: str | None) -> int:
    return {None: 0, "ask": 1, "deny": 2}[kind]


def check_segment(tokens: list[str], prev_op: str | None, next_tokens: list[str] | None, depth: int) -> tuple[str | None, str]:
    envs = env_assignments(tokens)
    tokens, sudo = strip_prefixes(tokens)
    if not tokens:
        return None, ""
    cmd, args = os.path.basename(tokens[0]), tokens[1:]
    flags = flags_of(args)
    positional = [a for a in args if not a.startswith("-")]
    found: list[tuple[str | None, str]] = []

    if sudo:
        found.append(("ask", "sudo runs with elevated rights; confirm this is needed"))

    if cmd in SHELLS and "-c" in args and depth < 3:                       # bash -c "..." : look inside
        inner = args[args.index("-c") + 1] if args.index("-c") + 1 < len(args) else ""
        found.append(evaluate_command(inner, depth + 1))

    if cmd == "rm":
        recursive = bool(flags & {"-r", "-R", "--recursive"})
        force = bool(flags & {"-f", "--force"})
        if recursive:
            unsafe = [t for t in positional if os.path.basename(t.rstrip("/")) not in SAFE_RM_TARGETS or t.startswith(("/", "~", "$", "..")) or "*" in t]
            if unsafe:
                found.append(("deny" if force else "ask", f"recursive delete of {', '.join(unsafe)}: only build and cache folders may be deleted this way"))

    if cmd == "git":
        sub_args = list(args)
        while sub_args and sub_args[0].startswith("-"):                    # skip git's own options: -C dir, -c k=v
            opt = sub_args.pop(0)
            if opt in ("-C", "-c") and sub_args:
                sub_args.pop(0)                                            # their value
        sub = sub_args[0] if sub_args else ""
        rest = sub_args[1:]
        rflags = flags_of(rest)
        if sub == "push":
            if rflags & {"--force", "-f", "--force-if-includes"} or any(a.startswith("+") for a in rest if not a.startswith("-")):
                found.append(("deny", "force-pushing rewrites shared history; use --force-with-lease after asking a human"))
            if "--no-verify" in rflags:
                found.append(("deny", "do not bypass git hooks"))
            if "--delete" in rflags or any(a.startswith(":") for a in rest):
                found.append(("ask", "this deletes a remote branch"))
            targets = [a.split(":")[-1] for a in rest if not a.startswith("-")]
            if any(t in ("main", "master") for t in targets):
                found.append(("ask", "pushing straight to main: open a pull request instead"))
        if sub == "commit" and (rflags & {"--no-verify", "-n"}):
            found.append(("deny", "do not bypass pre-commit hooks with --no-verify"))
        if sub == "reset" and "--hard" in rflags:
            found.append(("ask", "git reset --hard discards uncommitted work"))
        if sub == "clean" and rflags & {"-f", "--force"}:
            found.append(("ask", "git clean -f deletes untracked files permanently"))
        if sub in ("checkout", "restore") and ("." in rest or "--" in rest and "." in rest):
            found.append(("ask", "this discards every uncommitted change in the tree"))

    if cmd in ("curl", "wget") and next_tokens is not None:
        nxt, _ = strip_prefixes(next_tokens)
        if nxt and os.path.basename(nxt[0]) in SHELLS | {"python", "python3", "perl", "ruby", "node"}:
            found.append(("deny", "never pipe a download straight into an interpreter"))

    if cmd == "chmod" and any(a in ("777", "a+rwx") for a in args):
        found.append(("deny", "world-writable permissions are never the fix"))
    if cmd == "chown" and "-R" in args and any(a in ("/", "~") for a in positional):
        found.append(("deny", "recursive chown on the root or home directory"))

    if cmd in ("psql", "mysql", "sqlite3", "mongosh") and re.search(r"\b(drop\s+(database|table|schema)|truncate)\b", " ".join(args), re.IGNORECASE):
        found.append(("deny", "destructive SQL: run it yourself, deliberately, not through the agent"))

    if cmd in ("python", "python3") and any(a.endswith("manage.py") for a in args):
        settings = " ".join([envs.get("DJANGO_SETTINGS_MODULE", "")] + [a for a in args if a.startswith("--settings")])
        if "migrate" in args and re.search(r"prod|production|live", settings, re.IGNORECASE):
            found.append(("deny", "never run migrations against production from an agent session"))
        if "flush" in args or "sqlflush" in args:
            found.append(("ask", "manage.py flush deletes all data"))

    if cmd == "eas":
        sub = positional[0] if positional else ""
        joined = " ".join(args)
        if sub == "submit":
            found.append(("ask", "submitting to a store is a human release decision (Chapter 26)"))
        if sub == "build" and re.search(r"(--profile|-p)[ =]production", joined):
            found.append(("ask", "a production build is a release step"))
        if sub == "update" and re.search(r"--(channel|branch)[ =]production", joined):
            found.append(("ask", "publishing a production update reaches every user"))

    if cmd == "docker" and positional[:2] == ["system", "prune"]:
        found.append(("ask", "docker system prune removes images and volumes"))
    if cmd == "docker" and positional[:1] == ["compose"] and "down" in positional and "-v" in flags:
        found.append(("ask", "docker compose down -v deletes the database volume"))

    # writing to env files by redirection or tee
    for i, t in enumerate(tokens):
        if t in (">", ">>", ">|") and i + 1 < len(tokens) and ENV_FILE.search(tokens[i + 1]):
            found.append(("deny", "do not write secrets files from the shell"))
    if cmd == "tee" and any(ENV_FILE.search(p) for p in positional):
        found.append(("deny", "do not write secrets files from the shell"))

    best: tuple[str | None, str] = (None, "")
    for kind, reason in found:
        if rank(kind) > rank(best[0]):
            best = (kind, reason)
    return best


def evaluate_command(command: str, depth: int = 0) -> tuple[str | None, str]:
    """Returns ('deny'|'ask'|None, reason). Unparseable input asks rather than guessing."""
    try:
        segments = tokenize(command)
    except ValueError:
        return "ask", "this command could not be parsed safely"
    best: tuple[str | None, str] = (None, "")
    prev_op = None
    for i, seg in enumerate(segments):
        if seg[0] in OPERATORS:
            prev_op = seg[0]
            continue
        nxt = None
        if i + 2 < len(segments) and segments[i + 1][0] == "|":
            nxt = segments[i + 2]
        result = check_segment(seg, prev_op, nxt, depth)
        if rank(result[0]) > rank(best[0]):
            best = result
    for inner in re.findall(r"\$\(([^()]*)\)|`([^`]*)`", command):         # command substitution
        for piece in inner:
            if piece and depth < 3:
                result = evaluate_command(piece, depth + 1)
                if rank(result[0]) > rank(best[0]):
                    best = result
    return best


def handle(data: dict) -> int:
    if data.get("tool_name") != "Bash":
        return 0
    command = (data.get("tool_input") or {}).get("command", "")
    kind, reason = evaluate_command(command)
    if kind:
        print(json.dumps(pre_tool_decision(kind, reason)))
    return 0


if __name__ == "__main__":
    guard_main(handle)
