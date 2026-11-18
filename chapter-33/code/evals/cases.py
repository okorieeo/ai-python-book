"""Eval cases live in a JSONL file in Git: one JSON object per line, reviewed like code."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .checks import CHECKS


class CaseError(ValueError):
    pass


@dataclass(frozen=True)
class CheckSpec:
    type: str
    value: object = None


@dataclass(frozen=True)
class EvalCase:
    id: str
    input: str
    history: tuple[tuple[str, str], ...] = ()      # earlier (role, content) turns
    tags: tuple[str, ...] = ()
    checks: tuple[CheckSpec, ...] = ()
    rubric: str | None = None                      # when set, the LLM judge also grades this case
    notes: str = ""


def parse_case(obj: dict, where: str = "case") -> EvalCase:
    if not isinstance(obj, dict):
        raise CaseError(f"{where}: must be a JSON object")
    cid, text = obj.get("id"), obj.get("input")
    if not isinstance(cid, str) or not cid.strip():
        raise CaseError(f"{where}: 'id' must be a non-empty string")
    if not isinstance(text, str) or not text.strip():
        raise CaseError(f"{where} ({cid}): 'input' must be a non-empty string")
    checks = []
    for spec in obj.get("checks", []):
        if not isinstance(spec, dict) or spec.get("type") not in CHECKS:
            raise CaseError(f"{where} ({cid}): unknown check {spec!r}; valid types: {sorted(CHECKS)}")
        checks.append(CheckSpec(spec["type"], spec.get("value")))
    rubric = obj.get("rubric")
    if not checks and not rubric:
        raise CaseError(f"{where} ({cid}): a case with no checks and no rubric can never fail, so it proves nothing")
    history = []
    for turn in obj.get("history", []):
        if not (isinstance(turn, list) and len(turn) == 2 and turn[0] in ("user", "assistant") and isinstance(turn[1], str)):
            raise CaseError(f"{where} ({cid}): history entries must be [role, text] with role user or assistant")
        history.append((turn[0], turn[1]))
    tags = obj.get("tags", [])
    if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
        raise CaseError(f"{where} ({cid}): 'tags' must be a list of strings")
    return EvalCase(cid, text, tuple(history), tuple(tags), tuple(checks), rubric, str(obj.get("notes", "")))


def parse_lines(lines: Iterable[str]) -> list[EvalCase]:
    cases: list[EvalCase] = []
    seen: set[str] = set()
    for number, line in enumerate(lines, start=1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            obj = json.loads(line)
        except ValueError as exc:
            raise CaseError(f"line {number}: not valid JSON ({exc})") from None
        case = parse_case(obj, f"line {number}")
        if case.id in seen:
            raise CaseError(f"line {number}: duplicate id {case.id!r}")
        seen.add(case.id)
        cases.append(case)
    if not cases:
        raise CaseError("no cases found")
    return cases


def load_cases(path: str | Path) -> list[EvalCase]:
    return parse_lines(Path(path).read_text(encoding="utf-8").splitlines())
