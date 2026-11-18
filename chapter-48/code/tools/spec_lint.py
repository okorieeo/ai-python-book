"""Check that a feature spec is complete enough to build from.

Usage:  python -m tools.spec_lint docs/specs/share-conversation.md
Exit code 0 = ready, 1 = problems found.

A spec is "ready" when it has the sections below, every acceptance criterion has a
unique id (AC-1, AC-2, ...) and nothing is still marked TBD or TODO.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REQUIRED_SECTIONS = [
    "Problem",
    "Users and stories",
    "Acceptance criteria",
    "Non-goals",
    "Data",
    "API",
    "Security and privacy",
    "Open questions",
]
AC_LINE = re.compile(r"^\s*[-*]\s*\*{0,2}(AC-(\d+))\*{0,2}\s*[:.]", re.MULTILINE)
PLACEHOLDER = re.compile(r"\b(TBD|TODO|FIXME)\b")


def headings(text: str) -> list[str]:
    return [m.group(1).strip() for m in re.finditer(r"^#{1,3}\s+(.+?)\s*$", text, re.MULTILINE)]


def section_body(text: str, name: str) -> str:
    pattern = re.compile(rf"^#{{1,3}}\s+{re.escape(name)}\s*$(.*?)(?=^#{{1,3}}\s|\Z)", re.MULTILINE | re.DOTALL)
    m = pattern.search(text)
    return m.group(1) if m else ""


def lint(text: str) -> list[str]:
    problems: list[str] = []
    found = {h.lower() for h in headings(text)}
    for name in REQUIRED_SECTIONS:
        if name.lower() not in found:
            problems.append(f"missing section: {name}")
        elif not section_body(text, name).strip():
            problems.append(f"empty section: {name}")

    ids = [int(m.group(2)) for m in AC_LINE.finditer(text)]
    if not ids:
        problems.append("no acceptance criteria found (write them as '- AC-1: ...')")
    if len(ids) != len(set(ids)):
        problems.append("duplicate acceptance criterion ids")
    if ids and sorted(set(ids)) != list(range(1, max(ids) + 1)):
        problems.append("acceptance criterion ids are not consecutive from AC-1")

    open_q = section_body(text, "Open questions")
    unresolved = [l for l in open_q.splitlines() if l.strip().startswith(("-", "*")) and "[resolved]" not in l.lower()
                  and "none" not in l.lower()]
    if unresolved:
        problems.append(f"{len(unresolved)} open question(s) not marked [resolved]")

    for n, line in enumerate(text.splitlines(), start=1):
        if PLACEHOLDER.search(line):
            problems.append(f"line {n}: placeholder left in spec: {line.strip()[:60]}")
    return problems


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    problems = lint(Path(argv[1]).read_text(encoding="utf-8"))
    if problems:
        print(f"{argv[1]}: NOT READY")
        for p in problems:
            print("  -", p)
        return 1
    print(f"{argv[1]}: ready to build")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
