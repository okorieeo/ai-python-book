#!/usr/bin/env python3
"""
PreToolUse hook for Edit, Write and MultiEdit. Some files must never be changed by an agent: secrets, the .git
folder, lockfiles (regenerate them with the package manager), and migrations that already exist (they are history).
Changes to the guardrails themselves ask for a human.
"""
from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import json  # noqa: E402

from _common import guard_main, pre_tool_decision  # noqa: E402

LOCKFILES = {"package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "uv.lock", "pipfile.lock", "bun.lockb", "gemfile.lock"}
KEY_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".keystore", ".jks", ".p8"}
ENV_OK = {".env.example", ".env.sample", ".env.template"}
MIGRATION = re.compile(r"(^|/)migrations/\d{4}_[\w]+\.py$")


def evaluate(file_path: str, project_dir: str, exists=os.path.exists) -> tuple[str | None, str]:
    if not file_path:
        return None, ""
    raw = file_path.replace("\\", "/")
    full = os.path.normpath(raw if os.path.isabs(raw) else os.path.join(project_dir, raw)).replace("\\", "/")
    root = os.path.normpath(project_dir).replace("\\", "/")
    if full != root and not full.startswith(root.rstrip("/") + "/"):
        return "ask", "this file is outside the project folder"
    rel = full[len(root):].lstrip("/")
    parts = rel.split("/")
    name = parts[-1].lower()

    if ".git" in parts[:-1] or name == ".git":
        return "deny", "never edit the .git folder; use git commands"
    if name == ".env" or (name.startswith(".env.") and name not in ENV_OK):
        return "deny", "secrets files are edited by a human; put placeholders in .env.example instead"
    if os.path.splitext(name)[1] in KEY_SUFFIXES or name.startswith(("id_rsa", "id_ed25519")):
        return "deny", "key and certificate files must never be touched by an agent"
    if re.search(r"(service[-_]?account|credentials)[\w.-]*\.json$", name):
        return "deny", "credential files must never be touched by an agent"
    if "secrets" in parts[:-1]:
        return "deny", "the secrets folder is off limits"
    if name in LOCKFILES:
        return "deny", "do not hand-edit a lockfile; change the manifest and run the package manager"
    if MIGRATION.search(rel) and exists(full):
        return "deny", "an existing migration is history: create a new migration instead of editing it"
    if rel.startswith(".claude/hooks/") or re.fullmatch(r"\.claude/settings(\.local)?\.json", rel):
        return "ask", "this changes the guardrails themselves"
    return None, ""


def handle(data: dict) -> int:
    if data.get("tool_name") not in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
        return 0
    path = (data.get("tool_input") or {}).get("file_path", "")
    project = os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or os.getcwd()
    kind, reason = evaluate(path, project)
    if kind:
        print(json.dumps(pre_tool_decision(kind, reason)))
    return 0


if __name__ == "__main__":
    guard_main(handle)
