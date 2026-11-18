"""Turn a list of CaseResults into numbers a person can act on, and a yes/no a pipeline can act on."""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from .runner import CaseResult
from .stats import percentile, wilson_interval


@dataclass
class Summary:
    n: int
    passed: int
    failed: int
    errors: int
    pass_rate: float | None              # passed / (passed + failed); None when nothing was graded
    ci: tuple[float, float] | None
    by_tag: dict[str, dict] = field(default_factory=dict)
    mean_judge_score: float | None = None
    cost_micro_usd: int = 0
    unpriced: int = 0
    p50_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0

    @property
    def error_rate(self) -> float:
        return self.errors / self.n if self.n else 0.0


def summarize(results: list[CaseResult]) -> Summary:
    n = len(results)
    passed = sum(r.status == "pass" for r in results)
    failed = sum(r.status == "fail" for r in results)
    errors = sum(r.status == "error" for r in results)
    graded = passed + failed
    scores = [r.judge.verdict.score for r in results if r.judge is not None and r.judge.verdict is not None]
    by_tag: dict[str, dict] = {}
    for r in results:
        for tag in r.tags:
            slot = by_tag.setdefault(tag, {"pass": 0, "fail": 0, "error": 0})
            slot[r.status] += 1
    for slot in by_tag.values():
        g = slot["pass"] + slot["fail"]
        slot["pass_rate"] = slot["pass"] / g if g else None
    latencies = [r.latency_ms for r in results if r.error is None]
    return Summary(
        n=n, passed=passed, failed=failed, errors=errors,
        pass_rate=(passed / graded) if graded else None,
        ci=wilson_interval(passed, graded) if graded else None,
        by_tag=by_tag,
        mean_judge_score=(sum(scores) / len(scores)) if scores else None,
        cost_micro_usd=sum(r.cost_micro_usd or 0 for r in results),
        unpriced=sum(r.cost_micro_usd is None for r in results),
        p50_latency_ms=percentile(latencies, 50), p95_latency_ms=percentile(latencies, 95),
    )


@dataclass
class Comparison:
    regressions: list[str]
    improvements: list[str]
    unchanged: int
    not_comparable: list[str]            # an error in either run, or present in only one
    

def compare(base: list[CaseResult], cand: list[CaseResult]) -> Comparison:
    b = {r.case_id: r.status for r in base}
    c = {r.case_id: r.status for r in cand}
    reg, imp, same, skip = [], [], 0, []
    for cid in sorted(set(b) | set(c)):
        sb, sc = b.get(cid), c.get(cid)
        if sb is None or sc is None or "error" in (sb, sc):
            skip.append(cid)
        elif sb == "pass" and sc == "fail":
            reg.append(cid)
        elif sb == "fail" and sc == "pass":
            imp.append(cid)
        else:
            same += 1
    return Comparison(reg, imp, same, skip)


@dataclass
class GateResult:
    ok: bool
    reasons: list[str]


def gate(summary: Summary, comparison: Comparison | None = None, *, min_pass_rate: float,
         max_regressions: int = 0, max_error_rate: float = 0.05) -> GateResult:
    """The CI decision. Every reason that blocks a change is listed, so the failure message is the to-do list."""
    reasons: list[str] = []
    if summary.pass_rate is None:
        reasons.append("nothing could be graded")
    elif summary.pass_rate < min_pass_rate:
        reasons.append(f"pass rate {summary.pass_rate:.0%} is below the required {min_pass_rate:.0%}")
    if summary.error_rate > max_error_rate:
        reasons.append(f"{summary.errors} of {summary.n} cases errored ({summary.error_rate:.0%}); the run is not trustworthy")
    if comparison is not None and len(comparison.regressions) > max_regressions:
        reasons.append(f"{len(comparison.regressions)} regression(s): {', '.join(comparison.regressions)}")
    return GateResult(not reasons, reasons)


def results_to_json(results: list[CaseResult]) -> str:
    """The baseline file you commit: just enough to compare against next time."""
    rows = [{"id": r.case_id, "status": r.status, "tags": list(r.tags)} for r in results]
    return json.dumps(rows, indent=1, sort_keys=True)


def baseline_from_json(text: str) -> list[CaseResult]:
    out = []
    for row in json.loads(text):
        r = CaseResult(row["id"], tuple(row.get("tags", [])))
        if row["status"] == "error":
            r.error = "baseline error"
        elif row["status"] == "fail":
            from .checks import CheckResult
            r.checks = [CheckResult("baseline", False, "failed in baseline")]
        out.append(r)
    return out
