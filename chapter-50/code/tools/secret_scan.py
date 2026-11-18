"""Find secrets in code BEFORE they are committed.

Usage:
  git diff --cached | python -m tools.secret_scan            # staged changes (use as a pre-commit hook)
  python -m tools.secret_scan --files path1 path2 ...        # whole files or folders
Exit code 1 when something looks like a secret. Findings show only the first 4 characters.

It is a net with large holes: it knows common key formats and obvious assignments. A clean result
does not prove there are no secrets. Add `secretscan:allow` on a line to accept a known false positive.
"""
from __future__ import annotations

import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path

RULES: list[tuple[str, re.Pattern]] = [
    ("aws-access-key", re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("private-key", re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY")),
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
    ("slack-token", re.compile(r"\bxox[abposr]-[A-Za-z0-9-]{10,}")),
    ("stripe-or-paystack-live-key", re.compile(r"\b[sr]k_live_[0-9a-zA-Z]{16,}")),
    ("anthropic-key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}")),
    ("openai-style-key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{32,}")),
    ("google-api-key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")),
    ("password-in-url", re.compile(r"\b[a-z][a-z0-9+.-]*://[^/\s:@'\"]+:([^@\s/'\"]{4,})@")),
]
ASSIGNMENT = re.compile(
    r"""(?ix)\b([A-Za-z0-9_]*(?:api[_-]?key|secret|token|passwd|password|private[_-]?key|access[_-]?key)[A-Za-z0-9_]*)
        \s*[:=]\s*["']([^"'\s]{16,})["']"""
)
PLACEHOLDER = re.compile(r"(?i)(example|sample|changeme|change-me|your[_-]|xxx|placeholder|dummy|test|fake|<[^>]+>|\$\{|\{\{|process\.env|os\.environ|env\()")
COMMON_DUMMY = {"password", "pass", "passwd", "pwd", "secret", "admin", "root", "postgres", "user", "guest", "db"}
SKIP_NAMES = {".env.example", ".env.sample", ".env.template"}
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", ".next", "dist", "build", ".expo", "generated"}
TEXT_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx", ".json", ".yml", ".yaml", ".toml", ".ini", ".cfg", ".env", ".sh", ".md", ".txt", ".html", ".conf"}


@dataclass(frozen=True)
class Finding:
    file: str
    line: int
    rule: str
    preview: str

    def __str__(self):
        return f"{self.file}:{self.line}: {self.rule}: {self.preview}"


def entropy(s: str) -> float:
    if not s:
        return 0.0
    return -sum((s.count(c) / len(s)) * math.log2(s.count(c) / len(s)) for c in set(s))


def preview(secret: str) -> str:
    return secret[:4] + "*" * 6


def scan_line(line: str) -> list[tuple[str, str]]:
    if "secretscan:allow" in line:
        return []
    hits: list[tuple[str, str]] = []
    for name, pattern in RULES:
        m = pattern.search(line)
        if m:
            value = m.group(1) if name == "password-in-url" else m.group(0)
            if name == "password-in-url" and (PLACEHOLDER.search(value) or value.lower() in COMMON_DUMMY):
                continue
            hits.append((name, value))
    m = ASSIGNMENT.search(line)
    if m and not PLACEHOLDER.search(m.group(2)) and entropy(m.group(2)) >= 3.3:
        if not any(h[1] == m.group(2) for h in hits):
            hits.append((f"assignment to {m.group(1)}", m.group(2)))
    return hits


def scan_text(text: str, filename: str) -> list[Finding]:
    if Path(filename).name in SKIP_NAMES:
        return []
    out = []
    for n, line in enumerate(text.splitlines(), 1):
        for rule, value in scan_line(line):
            out.append(Finding(filename, n, rule, preview(value)))
    return out


def scan_diff(diff_text: str) -> list[Finding]:
    """Scan only the ADDED lines of a unified diff, reporting the line number in the new file."""
    out: list[Finding] = []
    current, new_line = "", 0
    for raw in diff_text.splitlines():
        if raw.startswith("+++ "):
            current = raw[4:].strip()
            current = current[2:] if current.startswith("b/") else current
        elif raw.startswith("@@"):
            m = re.search(r"\+(\d+)", raw)
            new_line = int(m.group(1)) - 1 if m else 0
        elif raw.startswith("+") and not raw.startswith("+++"):
            new_line += 1
            if Path(current).name in SKIP_NAMES:
                continue
            for rule, value in scan_line(raw[1:]):
                out.append(Finding(current, new_line, rule, preview(value)))
        elif not raw.startswith("-") and not raw.startswith("\\"):
            new_line += 1
    return out


def scan_paths(paths: list[Path]) -> list[Finding]:
    out: list[Finding] = []
    for root in paths:
        files = [root] if root.is_file() else [p for p in root.rglob("*") if p.is_file()]
        for f in files:
            if any(part in SKIP_DIRS for part in f.parts):
                continue
            if f.suffix not in TEXT_SUFFIXES and not f.name.startswith(".env"):
                continue
            try:
                out += scan_text(f.read_text(encoding="utf-8", errors="ignore"), str(f))
            except OSError:
                pass
    return out


def main(argv: list[str]) -> int:
    findings = scan_paths([Path(a) for a in argv[argv.index("--files") + 1:]]) if "--files" in argv else scan_diff(sys.stdin.read())
    if not findings:
        print("secret scan: nothing found (this does not prove there are no secrets)")
        return 0
    for f in findings:
        print(f)
    print(f"\n{len(findings)} possible secret(s). Remove them, rotate any that were real, and use environment variables.")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
