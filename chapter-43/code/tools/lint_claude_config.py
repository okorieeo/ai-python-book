"""Lint a project's Claude Code setup: CLAUDE.md and .claude/settings.json.

Run:  python tools/lint_claude_config.py [project_dir]
Exit status 1 when any error is found. It checks for common mistakes, it does not prove a setup is safe.
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

MAX_RECOMMENDED_LINES = 200
HARD_LIMIT_LINES = 400

VAGUE = (
    "write clean code", "format code properly", "follow best practices", "be careful",
    "keep files organized", "write good code", "use common sense", "test your changes",
)
SECRET_PATTERNS = (
    (re.compile(r"sk_(live|test)_[A-Za-z0-9]{8,}"), "a Stripe or Paystack style secret key"),
    (re.compile(r"sk-ant-[A-Za-z0-9_-]{8,}"), "an Anthropic API key"),
    (re.compile(r"AKIA[0-9A-Z]{12,}"), "an AWS access key id"),
    (re.compile(r"(?i)\b(password|passwd|secret|token)\s*[:=]\s*['\"]?[^\s'\"<>$]{6,}"), "a hardcoded credential"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "a private key"),
)
PERSONAL_PATH = re.compile(r"(/Users/[A-Za-z0-9._-]+|/home/[A-Za-z0-9._-]+|[A-Za-z]:\\Users\\)")
IMPORT = re.compile(r"(?<![`\w])@([\w./~-]+\.\w+|[\w./~-]*/[\w./~-]+)")


@dataclass(frozen=True)
class Finding:
    level: str     # error | warn | info
    code: str
    message: str

    def __str__(self) -> str:
        return f"{self.level.upper():5} {self.code:22} {self.message}"


def _strip_code_and_comments(text: str) -> str:
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    return re.sub(r"```.*?```", "", text, flags=re.S)


def lint_claude_md(text: str, *, base_dir: Path | None = None) -> list[Finding]:
    findings: list[Finding] = []
    lines = text.splitlines()
    if not text.strip():
        return [Finding("error", "empty", "CLAUDE.md is empty: run /init or write the build, test and run commands")]
    if len(lines) > HARD_LIMIT_LINES:
        findings.append(Finding("error", "too-long", f"{len(lines)} lines; move topic rules into .claude/rules/ or skills"))
    elif len(lines) > MAX_RECOMMENDED_LINES:
        findings.append(Finding("warn", "long", f"{len(lines)} lines; the guidance is under {MAX_RECOMMENDED_LINES}"))

    prose = _strip_code_and_comments(text)
    lowered = prose.lower()
    for phrase in VAGUE:
        if phrase in lowered:
            findings.append(Finding("warn", "vague", f"'{phrase}' is not checkable; say the exact command or rule instead"))

    for pattern, what in SECRET_PATTERNS:
        if pattern.search(text):
            findings.append(Finding("error", "secret", f"looks like {what}: never put secrets in CLAUDE.md (it is committed)"))

    if PERSONAL_PATH.search(text):
        findings.append(Finding("warn", "personal-path", "contains a path from one person's machine; use repository-relative paths"))

    commands = re.findall(r"`([^`\n]+)`", text)
    tool = r"(python|python3|pip|npm|pnpm|yarn|npx|docker|make|pytest|ruff|git|celery|uv|poetry|node|expo|eas|tsc)"
    runnable = [c for c in commands if re.search(r"(^|&&\s*|;\s*|\|\|\s*)(cd\s+\S+\s*&&\s*)?" + tool + r"\b", c)]
    if not runnable:
        findings.append(Finding("warn", "no-commands", "no build, test or run commands in backticks: Claude cannot verify its own work"))
    elif not any(re.search(r"\b(test|pytest|check|lint)\b", c) for c in runnable):
        findings.append(Finding("warn", "no-test-command", "no test or lint command found: add how to run the tests"))

    seen: dict[str, int] = {}
    for n, line in enumerate(lines, 1):
        key = line.strip().lower()
        if len(key) > 25 and key.startswith(("-", "*")):
            if key in seen:
                findings.append(Finding("warn", "duplicate", f"line {n} repeats line {seen[key]}"))
            seen.setdefault(key, n)

    if base_dir is not None:
        for m in IMPORT.finditer(prose):
            target = m.group(1)
            if target.startswith(("~", "/")):
                continue
            if not (base_dir / target).exists():
                findings.append(Finding("error", "missing-import", f"@{target} does not exist relative to CLAUDE.md"))
    return findings


def lint_settings(text: str, *, scope: str = "project") -> list[Finding]:
    """scope: 'project' (.claude/settings.json), 'local' or 'user'."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return [Finding("error", "invalid-json", f"settings file is not valid JSON: {exc.msg} (line {exc.lineno})")]
    if not isinstance(data, dict):
        return [Finding("error", "invalid-json", "settings file must be a JSON object")]

    findings: list[Finding] = []
    perms = data.get("permissions") or {}
    allow, deny, ask = (perms.get(k) or [] for k in ("allow", "deny", "ask"))

    for rule in allow:
        if rule in ("Bash", "Bash(*)", "PowerShell", "PowerShell(*)"):
            findings.append(Finding("error", "allow-all-shell", f"'{rule}' lets Claude run any command without asking"))
        elif re.match(r"^Bash\((python|node|bash|sh|zsh|ruby|perl)[^ )]*\*", rule) or re.match(r"^Bash\((python|node|bash|sh|zsh)\s\*\)", rule):
            findings.append(Finding("warn", "allow-interpreter", f"'{rule}' approves arbitrary code through an interpreter"))
        elif re.match(r"^Bash\(rm\b", rule) or re.match(r"^Bash\(sudo\b", rule) or re.match(r"^Bash\(curl\b.*\|", rule):
            findings.append(Finding("error", "allow-dangerous", f"'{rule}' should never be pre-approved"))
        elif re.match(r"^Bash\(\w+ \* \w", rule):
            findings.append(Finding("warn", "wildcard-before-subcommand", f"'{rule}' has * before the rest of the command; put it after the subcommand"))
        if rule.startswith(("Write(", "NotebookEdit(", "Glob(")):
            findings.append(Finding("warn", "never-matches", f"'{rule}' never matches: use Edit(path) or Read(path)"))

    all_path_rules = [r for r in (*allow, *deny, *ask) if re.match(r"^(Read|Edit)\(/[A-Za-z]", r)]
    for rule in all_path_rules:
        if re.match(r"^(Read|Edit)\(/(Users|home|etc|var|tmp|mnt)/", rule):
            findings.append(Finding("warn", "single-slash-path", f"'{rule}': one leading slash is relative to the settings file; use // for an absolute path"))

    protects_env = any(re.match(r"^Read\((\./|\*\*/)?\.env", r) or r.startswith("Read(.env") for r in deny)
    if not protects_env:
        findings.append(Finding("warn", "env-not-denied", "no Read deny rule for .env files: add \"Read(./.env)\" and \"Read(./.env.*)\""))
    if not any(r.startswith("Bash(git push") for r in (*deny, *ask)):
        findings.append(Finding("info", "push-not-gated", "git push is not in deny or ask: you may want a human to push"))

    mode = perms.get("defaultMode")
    if scope in ("project", "local") and mode == "bypassPermissions":
        findings.append(Finding("error", "bypass-in-project", "bypassPermissions in a project file is ignored by Claude Code and unsafe to ask for"))
    if scope in ("project", "local") and mode == "auto":
        findings.append(Finding("warn", "auto-in-project", "defaultMode 'auto' does not take effect from project settings; set it in ~/.claude/settings.json"))
    if mode and mode not in ("default", "manual", "acceptEdits", "plan", "auto", "dontAsk", "bypassPermissions"):
        findings.append(Finding("error", "unknown-mode", f"unknown defaultMode {mode!r}"))

    for rule in ("env",):
        env = data.get(rule) or {}
        for key, value in env.items():
            if isinstance(value, str) and any(p.search(value) for p, _ in SECRET_PATTERNS):
                findings.append(Finding("error", "secret", f"env.{key} looks like a secret in a file that is committed"))
    return findings


def lint_project(root: Path) -> list[tuple[str, Finding]]:
    out: list[tuple[str, Finding]] = []
    claude_md = next((p for p in (root / "CLAUDE.md", root / ".claude" / "CLAUDE.md") if p.exists()), None)
    if claude_md is None:
        out.append(("CLAUDE.md", Finding("warn", "missing", "no CLAUDE.md: run /init in Claude Code, then trim it")))
    else:
        out += [(str(claude_md.relative_to(root)), f) for f in lint_claude_md(claude_md.read_text(encoding="utf-8"), base_dir=claude_md.parent)]
    for name, scope in ((".claude/settings.json", "project"), (".claude/settings.local.json", "local")):
        path = root / name
        if path.exists():
            out += [(name, f) for f in lint_settings(path.read_text(encoding="utf-8"), scope=scope)]
    for rule in sorted((root / ".claude" / "rules").glob("*.md")) if (root / ".claude" / "rules").exists() else []:
        text = rule.read_text(encoding="utf-8")
        rel = str(rule.relative_to(root))
        if len(text.splitlines()) > MAX_RECOMMENDED_LINES:
            out.append((rel, Finding("warn", "long", "rule file is long; split it by topic")))
        for pattern, what in SECRET_PATTERNS:
            if pattern.search(text):
                out.append((rel, Finding("error", "secret", f"looks like {what}")))
    gi = root / ".gitignore"
    ignored = gi.read_text(encoding="utf-8") if gi.exists() else ""
    for needed in ("CLAUDE.local.md", ".claude/settings.local.json"):
        if (root / needed).exists() and needed not in ignored:
            out.append((".gitignore", Finding("error", "personal-file-tracked", f"{needed} exists but is not in .gitignore")))
    return out


def main(argv: list[str] | None = None) -> int:
    root = Path((argv or sys.argv[1:] or ["."])[0]).resolve()
    results = lint_project(root)
    for name, finding in results:
        print(f"{name:34} {finding}")
    errors = sum(1 for _, f in results if f.level == "error")
    warns = sum(1 for _, f in results if f.level == "warn")
    print(f"\n{errors} error(s), {warns} warning(s), {len(results) - errors - warns} note(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
