"""Traceability: every acceptance criterion in the spec must be mentioned by at least one test.

Usage:  python -m tools.trace_check docs/specs/share-conversation.md backend web mobile

A test "covers" AC-3 when the text AC-3 appears in a test file (a comment, a docstring,
a test name such as test_ac3_..., or a describe/it title). Test files are files named test_*.py, *_test.py,
tests.py, *.test.ts(x), *.spec.ts(x), or any file inside a tests or __tests__ folder.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SKIP_DIRS = {"node_modules", ".venv", "venv", ".git", "__pycache__", ".next", "dist", "build", ".expo"}
TEXT_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx"}
AC_DEF = re.compile(r"^\s*[-*]\s*\*{0,2}AC-(\d+)\*{0,2}\s*[:.]\s*(.*)$", re.MULTILINE)
AC_REF = re.compile(r"(?<![A-Za-z0-9])AC[-_ ]?(\d+)(?!\d)", re.IGNORECASE)  # matches AC-3, AC3 and test_ac3_x


def acceptance_criteria(spec_text: str) -> dict[int, str]:
    return {int(m.group(1)): m.group(2).strip() for m in AC_DEF.finditer(spec_text)}


def is_test_file(path: Path) -> bool:
    name = path.name.lower()
    return (
        name.startswith("test_")
        or name.endswith(("_test.py", "_tests.py"))
        or name == "tests.py"
        or ".test." in name
        or ".spec." in name
        or "__tests__" in path.parts
        or "tests" in path.parts
    )


def iter_test_files(roots: list[Path]):
    for root in roots:
        if root.is_file():
            if is_test_file(root):
                yield root
            continue
        for path in root.rglob("*"):
            if any(part in SKIP_DIRS for part in path.parts):
                continue
            if path.is_file() and path.suffix in TEXT_SUFFIXES and is_test_file(path):
                yield path


def coverage(spec_text: str, roots: list[Path]) -> tuple[dict[int, str], dict[int, set[str]]]:
    criteria = acceptance_criteria(spec_text)
    covered: dict[int, set[str]] = {n: set() for n in criteria}
    for path in iter_test_files(roots):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for m in AC_REF.finditer(text):
            n = int(m.group(1))
            if n in covered:
                covered[n].add(str(path))
    return criteria, covered


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(__doc__)
        return 2
    spec_text = Path(argv[1]).read_text(encoding="utf-8")
    criteria, covered = coverage(spec_text, [Path(p) for p in argv[2:]])
    missing = [n for n, files in covered.items() if not files]
    for n in sorted(criteria):
        mark = "ok     " if covered[n] else "MISSING"
        print(f"AC-{n:<2} {mark} {criteria[n][:70]}")
    print(f"\n{len(criteria) - len(missing)} of {len(criteria)} criteria have a test")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
