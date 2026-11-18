#!/usr/bin/env python3
"""
Check the PLAN.md Claude writes before you let it build anything. A plan that lists files that do not exist, has
twenty steps, or has no way to verify itself is a plan to stop and fix, and it is cheaper to catch here than in code.

    python tools/planlint.py PLAN.md [--repo .]
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

SECTIONS = {
    "goal": r"(?:goal|summary|objective)",
    "files": r"(?:files?(?: to (?:change|touch|edit))?|affected files)",
    "steps": r"(?:steps?|implementation (?:steps|plan)|plan)",
    "verification": r"(?:verification|testing|tests?(?: plan)?|how to verify|acceptance(?: criteria)?)",
    "risks": r"(?:risks?(?: (?:and|&) (?:open )?(?:questions?|unknowns?))?|open questions?|questions?|unknowns?)",
    "out_of_scope": r"(?:out of scope|non-goals?|not (?:doing|included))",
}
MAX_STEPS = 12


@dataclass
class Finding:
    id: str
    severity: str
    message: str


@dataclass
class PlanResult:
    sections: dict[str, str]
    findings: list[Finding] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(f.severity == "error" for f in self.findings)


def split_sections(text: str) -> dict[str, str]:
    heads = list(re.finditer(r"^#{1,4}\s*(.+?)\s*$", text, re.MULTILINE))
    found: dict[str, str] = {}
    for i, h in enumerate(heads):
        title = re.sub(r"[`*:]", "", h.group(1)).strip().lower()
        body = text[h.end(): heads[i + 1].start() if i + 1 < len(heads) else len(text)].strip()
        for key, pattern in SECTIONS.items():
            if key not in found and re.fullmatch(pattern, title):
                found[key] = body
    return found


def lint_plan(text: str, repo_root: str | Path | None = None) -> PlanResult:
    sections = split_sections(text)
    result = PlanResult(sections)
    add = lambda i, sev, msg: result.findings.append(Finding(i, sev, msg))
    for key in SECTIONS:
        if key not in sections or not sections[key].strip():
            add(f"missing-{key}", "error", f"The plan has no '{key.replace('_', ' ')}' section (or it is empty).")

    steps = [s for s in re.findall(r"^\s*\d+[.)]\s+(.+)$", sections.get("steps", ""), re.MULTILINE)]
    if "steps" in sections:
        if len(steps) < 2:
            add("not-a-plan", "error", "Fewer than two numbered steps: this is a single action, not a plan.")
        if len(steps) > MAX_STEPS:
            add("too-many-steps", "error", f"{len(steps)} steps is too big to review. Split the work into separate plans.")
        for n, step in enumerate(steps, start=1):
            if not re.search(r"done when|verify|verified by|check:|test", step, re.IGNORECASE):
                add("step-unverifiable", "warn", f"Step {n} has no way to tell it is finished: {step[:60]!r}")

    files_body = sections.get("files", "")
    paths = []
    for line in files_body.splitlines():
        for m in re.finditer(r"`([^`\s]+\.[A-Za-z0-9]+|[^`\s]+/[^`\s]*)`", line):
            paths.append((m.group(1), bool(re.search(r"\((?:new|create|will be created)\)|\bnew file\b", line, re.IGNORECASE))))
    if "files" in sections and not paths:
        add("files-unlisted", "error", "The files section names no files in backticks, so there is nothing to check or review.")
    if repo_root is not None:
        root = Path(repo_root)
        for path, is_new in paths:
            if not is_new and not (root / path).exists():
                add("missing-file", "error", f"`{path}` does not exist and is not marked (new): the plan may be built on a guess.")

    open_questions = [l for l in sections.get("risks", "").splitlines() if l.strip().endswith("?")]
    if open_questions:
        add("open-questions", "warn", f"{len(open_questions)} open question(s): answer them before building.")
    return result


def main(argv: list[str]) -> int:
    repo = "."
    if "--repo" in argv:
        i = argv.index("--repo")
        repo = argv[i + 1]
        del argv[i:i + 2]
    res = lint_plan(Path(argv[0]).read_text(encoding="utf-8"), repo)
    for f in res.findings:
        print(f"{f.severity:5} {f.id}: {f.message}")
    print("PLAN OK" if res.ok else "PLAN NEEDS WORK")
    return 0 if res.ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
