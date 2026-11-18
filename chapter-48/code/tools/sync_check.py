"""Find API calls in web and mobile code that the contract does not know about.

Usage:  python -m tools.sync_check contracts/openapi.json web/src mobile/src

It looks for string literals and template literals that start with /api/ and checks that
each one matches a path in the contract ({id} and ${id} both count as a parameter).
It cannot prove a call is correct. It catches the cheap, common failure: a typo, a
renamed route, or an endpoint that exists only in someone's head.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from .openapi_util import load

SKIP_DIRS = {"node_modules", ".next", ".expo", "dist", "build", ".git", "generated"}
SOURCE_SUFFIXES = {".ts", ".tsx", ".js", ".jsx"}
LITERAL = re.compile(r"""[`'"](/api/[^`'"\s?]*)""")


def contract_patterns(doc: dict) -> list[re.Pattern]:
    patterns = []
    for path in doc.get("paths", {}):
        regex = re.escape(path)
        regex = re.sub(r"\\\{[^}]+\\\}", r"[^/]+", regex)
        patterns.append(re.compile(rf"^{regex}$"))
    return patterns


def normalise(url: str) -> str:
    """'/api/v1/x/${id}/share/' -> '/api/v1/x/PARAM/share/'; also add a trailing slash."""
    url = re.sub(r"\$\{[^}]*\}", "PARAM", url)
    return url if url.endswith("/") else url + "/"


def find_calls(root: Path):
    for path in root.rglob("*"):
        if any(part in SKIP_DIRS for part in path.parts) or path.suffix not in SOURCE_SUFFIXES:
            continue
        for n, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), start=1):
            for m in LITERAL.finditer(line):
                yield path, n, m.group(1)


def check(doc: dict, roots: list[Path]) -> list[str]:
    patterns = contract_patterns(doc)
    problems = []
    for root in roots:
        for path, n, url in find_calls(root):
            if not any(p.match(normalise(url)) for p in patterns):
                problems.append(f"{path}:{n}: {url} is not in the contract")
    return problems


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(__doc__)
        return 2
    problems = check(load(argv[1]), [Path(p) for p in argv[2:]])
    if problems:
        print(f"{len(problems)} call(s) the contract does not describe:")
        for p in problems:
            print("  -", p)
        return 1
    print("every API call in the code is described by the contract")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
