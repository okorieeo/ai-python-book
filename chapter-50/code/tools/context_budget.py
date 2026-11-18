"""Estimate how much of Claude's context window your files would use, and find the noisy ones.

Usage:  python -m tools.context_budget [folder] [--top 10] [--window 200000]

Tokens are ESTIMATED as characters / 4 (a rough rule for English text and code). Real counts differ by
model and content: use it to find the heavy files and to compare, not as an exact bill.
It also lists files that are almost never worth putting in front of Claude (lockfiles, minified or generated
code, logs, data dumps, source maps) and prints permission rules to keep them out.
"""
from __future__ import annotations

import fnmatch
import sys
from dataclasses import dataclass
from pathlib import Path

SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", ".next", "dist", "build", ".expo", "coverage", ".mypy_cache", ".pytest_cache"}
NOISY = [
    ("lockfile", ["package-lock.json", "pnpm-lock.yaml", "yarn.lock", "poetry.lock", "uv.lock", "Pipfile.lock", "requirements.lock*"]),
    ("minified or map", ["*.min.js", "*.min.css", "*.map", "*.bundle.js"]),
    ("generated code", ["*/generated/*", "*_pb2.py", "*.generated.*"]),
    ("log or dump", ["*.log", "*.ndjson", "*.sql", "*.dump", "*.csv", "*.tsv"]),
]
TEXT_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx", ".json", ".md", ".txt", ".yml", ".yaml", ".toml", ".html", ".css", ".sh", ".sql", ".csv", ".log", ".ndjson", ".map", ".lock", ".ini", ".cfg"}


@dataclass(frozen=True)
class Entry:
    path: str
    chars: int
    noisy: str = ""

    @property
    def tokens(self) -> int:
        return self.chars // 4


def classify(rel: str) -> str:
    name = rel.rsplit("/", 1)[-1]
    for label, patterns in NOISY:
        if any(fnmatch.fnmatch(name, p) or fnmatch.fnmatch("/" + rel, p) for p in patterns):
            return label
    return ""


def scan(root: Path) -> list[Entry]:
    out = []
    for f in root.rglob("*"):
        if not f.is_file() or any(p in SKIP_DIRS for p in f.relative_to(root).parts):
            continue
        if f.suffix not in TEXT_SUFFIXES and f.name not in ("Dockerfile",) and "lock" not in f.name:
            continue
        rel = str(f.relative_to(root)).replace("\\", "/")
        try:
            chars = len(f.read_text(encoding="utf-8", errors="ignore"))
        except OSError:
            continue
        out.append(Entry(rel, chars, classify(rel)))
    return sorted(out, key=lambda e: -e.chars)


def deny_rules(entries: list[Entry]) -> list[str]:
    rules = []
    for e in entries:
        if e.noisy and e.tokens >= 500:
            rules.append(f'"Read(./{e.path})"')
    return rules


def main(argv: list[str]) -> int:
    root = Path(next((a for a in argv[1:] if not a.startswith("--") and not a.isdigit()), "."))
    top = int(argv[argv.index("--top") + 1]) if "--top" in argv else 10
    window = int(argv[argv.index("--window") + 1]) if "--window" in argv else 200_000
    entries = scan(root)
    total = sum(e.tokens for e in entries)
    useful = sum(e.tokens for e in entries if not e.noisy)
    print(f"{len(entries)} text files, about {total:,} tokens in all ({100 * total / window:.0f}% of a {window:,}-token window)")
    print(f"without noisy files: about {useful:,} tokens\n")
    print(f"Heaviest {top} files (estimated tokens):")
    for e in entries[:top]:
        print(f"  {e.tokens:>8,}  {e.path}" + (f"   <- {e.noisy}" if e.noisy else ""))
    rules = deny_rules(entries)
    if rules:
        print("\nConsider keeping these out of Claude's reach (settings.json, permissions.deny):")
        for r in rules[:10]:
            print("  " + r)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
