"""A referee for bug-fix diffs: did the fix come with a test, and does it contain the usual smells?

Usage:
  git diff --cached | python -m tools.fix_gate          # staged changes
  git diff main...HEAD | python -m tools.fix_gate       # a whole branch
Exit code 1 when an ERROR is found. WARNINGs are printed for you to judge.

ERROR   source changed but no test file changed       (a fix without a regression test)
ERROR   a generated file was edited by hand
ERROR   a check was bypassed or a test disabled (skip, xit, eslint-disable, @ts-ignore, --no-verify)
ERROR   an exception is swallowed (bare except, `except Exception: pass`, empty catch block)
WARNING assertions were removed from a test
WARNING sleep() added, print/console.log added, dependency file changed, diff larger than 300 lines
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field

TEST_PATH = re.compile(r"(^|/)(tests?|__tests__)/|(^|/)test_[^/]*\.py$|_tests?\.py$|\.(test|spec)\.[jt]sx?$")
DOC_PATH = re.compile(r"\.(md|txt|rst)$|(^|/)docs?/")
DEP_FILES = ("package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "requirements", "poetry.lock", "pyproject.toml")
CODE_SUFFIXES = (".py", ".ts", ".tsx", ".js", ".jsx")

ERROR_PATTERNS = [
    (re.compile(r"@unittest\.skip|pytest\.mark\.skip|\bxit\(|\bxdescribe\(|\b(it|test|describe)\.skip\("), "test disabled"),
    (re.compile(r"eslint-disable|@ts-ignore|@ts-nocheck|# type: ignore|# noqa|# pylint: disable"), "check silenced"),
    (re.compile(r"--no-verify"), "git hook bypassed"),
    (re.compile(r"^\s*except\s*:\s*$|^\s*except\s+(Base)?Exception\s*(as\s+\w+)?\s*:\s*(pass)?\s*$"), "broad except (check what it swallows)"),
    (re.compile(r"catch\s*(\([^)]*\))?\s*\{\s*\}"), "empty catch block"),
]
WARN_PATTERNS = [
    (re.compile(r"\btime\.sleep\(|\bsetTimeout\(|\bawait sleep\("), "sleep or timeout added (hiding a race?)"),
    (re.compile(r"^\s*print\(|console\.log\("), "debug output added"),
]


@dataclass
class Finding:
    level: str
    where: str
    what: str

    def __str__(self):
        return f"{self.level:<7} {self.where}: {self.what}"


@dataclass
class FileDiff:
    path: str
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)


def parse_diff(text: str) -> list[FileDiff]:
    files: list[FileDiff] = []
    cur: FileDiff | None = None
    for line in text.splitlines():
        if line.startswith("+++ "):
            path = line[4:].strip()
            path = path[2:] if path.startswith("b/") else path
            if path == "/dev/null":
                continue
            cur = FileDiff(path)
            files.append(cur)
        elif line.startswith("--- ") or line.startswith("diff --git") or line.startswith("@@"):
            continue
        elif cur is not None and line.startswith("+"):
            cur.added.append(line[1:])
        elif cur is not None and line.startswith("-"):
            cur.removed.append(line[1:])
    return files


def is_test(path: str) -> bool:
    return bool(TEST_PATH.search(path))


def is_source(path: str) -> bool:
    return path.endswith(CODE_SUFFIXES) and not is_test(path) and not DOC_PATH.search(path)


def count_asserts(lines: list[str]) -> int:
    return sum(bool(re.search(r"\bassert\w*\(|\bassert\s|\bexpect\(|\.toBe|\.toEqual|\.toHaveBeen", l)) for l in lines)


def check(diff_text: str) -> list[Finding]:
    files = parse_diff(diff_text)
    out: list[Finding] = []
    src = [f for f in files if is_source(f.path)]
    tests = [f for f in files if is_test(f.path)]
    if src and not tests:
        out.append(Finding("ERROR", ", ".join(f.path for f in src[:3]), "source changed but no test file changed: add a regression test"))
    for f in files:
        if "/generated/" in f"/{f.path}":
            out.append(Finding("ERROR", f.path, "generated file edited by hand: regenerate it instead"))
        if any(f.path.endswith(d) or d in f.path for d in DEP_FILES) and not f.path.endswith(".md"):
            out.append(Finding("WARNING", f.path, "dependency file changed: is a new package really needed?"))
        if not f.path.endswith(CODE_SUFFIXES + (".yml", ".yaml", ".sh", ".json", ".toml")):
            continue
        for line in f.added:
            for pattern, what in ERROR_PATTERNS:
                if pattern.search(line):
                    out.append(Finding("ERROR", f.path, f"{what}: {line.strip()[:70]}"))
            if not is_test(f.path):
                for pattern, what in WARN_PATTERNS:
                    if pattern.search(line):
                        out.append(Finding("WARNING", f.path, f"{what}: {line.strip()[:70]}"))
        if is_test(f.path) and count_asserts(f.removed) > count_asserts(f.added):
            out.append(Finding("WARNING", f.path, f"assertions removed ({count_asserts(f.removed)} out, {count_asserts(f.added)} in): was a test weakened?"))
    # an "except ...:" followed on the next added line by pass is the classic swallow
    for f in files:
        for a, b in zip(f.added, f.added[1:]):
            if re.match(r"^\s*except\b.*:\s*$", a) and b.strip() == "pass":
                out.append(Finding("ERROR", f.path, f"exception swallowed: {a.strip()} / pass"))
    changed = sum(len(f.added) + len(f.removed) for f in files)
    if changed > 300:
        out.append(Finding("WARNING", "whole diff", f"{changed} changed lines: a bug fix this large is usually more than one change"))
    seen, unique = set(), []
    for f in out:
        key = (f.level, f.where, f.what)
        if key not in seen:
            seen.add(key)
            unique.append(f)
    return sorted(unique, key=lambda f: (f.level != "ERROR", f.where))


def main(argv: list[str]) -> int:
    findings = check(sys.stdin.read())
    if not findings:
        print("fix gate: no findings")
        return 0
    for f in findings:
        print(f)
    errors = sum(f.level == "ERROR" for f in findings)
    print(f"\n{errors} error(s), {len(findings) - errors} warning(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
