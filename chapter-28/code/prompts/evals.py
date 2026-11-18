"""A small evaluation harness: cases, checks, a report and a comparison table."""
from dataclasses import dataclass, field
from typing import Callable

from .structured import StructuredOutputError, extract_json, validate


@dataclass
class EvalCase:
    id: str
    variables: dict
    checks: list = field(default_factory=list)  # each: fn(output_text) -> None or an error string
    tags: tuple = ()


# ---- checks: each returns None when the output passes, or a short failure message -------

def valid_json(schema: dict) -> Callable:
    def check(output: str):
        try:
            problems = validate(extract_json(output), schema)
        except StructuredOutputError as error:
            return str(error)
        return "; ".join(problems) if problems else None
    return check


def is_pure_json() -> Callable:
    """The whole reply must be JSON: no 'Sure! Here you go' before it, no fences."""
    import json

    def check(output: str):
        try:
            json.loads(output)
        except ValueError:
            return "reply is not pure JSON"
        return None
    return check


def contains(text: str) -> Callable:
    return lambda output: None if text.lower() in output.lower() else f"missing {text!r}"


def not_contains(text: str) -> Callable:
    return lambda output: f"must not contain {text!r}" if text.lower() in output.lower() else None


def max_words(limit: int) -> Callable:
    return lambda output: None if len(output.split()) <= limit else f"more than {limit} words"


def json_field(path: str, test: Callable, description: str) -> Callable:
    """Check one top-level JSON field with a function, e.g. json_field("title", lambda v: len(v) <= 60, "title <= 60")."""
    def check(output: str):
        try:
            value = extract_json(output)[path]
        except (StructuredOutputError, KeyError, TypeError):
            return f"field {path!r} not found"
        return None if test(value) else f"{path}: {description}"
    return check


# ---- running and reporting ----------------------------------------------------------------

@dataclass
class CaseResult:
    case_id: str
    passed: bool
    failures: list
    output: str


@dataclass
class EvalReport:
    label: str
    results: list

    @property
    def passed(self) -> int:
        return sum(r.passed for r in self.results)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total else 0.0

    def failing_ids(self) -> list:
        return [r.case_id for r in self.results if not r.passed]


def run_eval(llm, prompt_version, cases: list, *, label: str = "", max_tokens: int = 800) -> EvalReport:
    """Render the prompt for each case, call the model once, and apply the case's checks."""
    results = []
    for case in cases:
        prompt = prompt_version.render(case.variables)
        reply = llm.complete(system=prompt.system, messages=prompt.messages, max_tokens=max_tokens)
        failures = [msg for check in case.checks if (msg := check(reply.text))]
        results.append(CaseResult(case.id, not failures, failures, reply.text))
    return EvalReport(label or prompt_version.prompt_id, results)


def format_comparison(reports: list) -> str:
    """A plain-text table: one row per case, one column per prompt version."""
    ids = [r.case_id for r in reports[0].results]
    width = max(len(i) for i in ids + ["case"])
    header = "case".ljust(width) + "  " + "  ".join(rep.label.split("#")[0].ljust(27) for rep in reports)
    lines = [header, "-" * len(header)]
    for i, case_id in enumerate(ids):
        cells = []
        for rep in reports:
            res = rep.results[i]
            cells.append(("PASS" if res.passed else "FAIL: " + res.failures[0][:17]).ljust(27))
        lines.append(case_id.ljust(width) + "  " + "  ".join(cells))
    lines.append("-" * len(header))
    lines.append("pass rate".ljust(width) + "  " + "  ".join(f"{r.passed}/{r.total}".ljust(27) for r in reports))
    return "\n".join(lines)
