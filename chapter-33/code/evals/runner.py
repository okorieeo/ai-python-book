"""
Run every eval case against a system under test and grade the answers.

The system under test is any async function (EvalCase -> GenOutput). In production-like runs it wraps your
real ChatService; in tests it is a scripted function. The runner knows nothing about either.

One rule matters more than the rest: an ERROR (timeout, provider outage, judge that returned nonsense) is
not a FAIL. If infrastructure trouble is counted as bad answers, a flaky network looks like a quality
regression and people stop trusting the numbers.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from ai.dto import Usage
from ai.pricing import ModelPrice, cost_or_none

from .cases import EvalCase
from .checks import CheckResult, run_check
from .judge import JudgeResult


@dataclass(frozen=True)
class GenOutput:
    text: str
    usage: Usage = field(default_factory=Usage)
    model: str = ""


Generator = Callable[[EvalCase], Awaitable[GenOutput]]
JudgeFn = Callable[[EvalCase, str], Awaitable[JudgeResult]]


@dataclass
class CaseResult:
    case_id: str
    tags: tuple[str, ...]
    output: str = ""
    checks: list[CheckResult] = field(default_factory=list)
    judge: JudgeResult | None = None
    usage: Usage = field(default_factory=Usage)
    cost_micro_usd: int | None = 0
    latency_ms: float = 0.0
    error: str | None = None

    @property
    def status(self) -> str:
        if self.error is not None or (self.judge is not None and self.judge.error is not None):
            return "error"
        if any(not c.passed for c in self.checks):
            return "fail"
        if self.judge is not None and not self.judge.passed:
            return "fail"
        return "pass"

    @property
    def failures(self) -> list[str]:
        out = [f"{c.type}: {c.detail}" for c in self.checks if not c.passed]
        if self.judge is not None and self.judge.verdict is not None and not self.judge.passed:
            out.append(f"judge score {self.judge.verdict.score}: {self.judge.verdict.reasoning}")
        return out


async def run_eval(
    cases: list[EvalCase],
    generate: Generator,
    *,
    judge_fn: JudgeFn | None = None,
    concurrency: int = 4,
    case_timeout: float = 60.0,
    clock: Callable[[], float] = time.monotonic,
    prices: dict[str, ModelPrice] | None = None,
) -> list[CaseResult]:
    """Results come back in the same order as `cases`, however the work was scheduled."""
    sem = asyncio.Semaphore(max(1, concurrency))

    async def one(case: EvalCase) -> CaseResult:
        result = CaseResult(case.id, case.tags)
        async with sem:
            started = clock()
            try:
                out = await asyncio.wait_for(generate(case), timeout=case_timeout)
            except asyncio.TimeoutError:
                result.error = f"timed out after {case_timeout}s"
                result.latency_ms = (clock() - started) * 1000
                return result
            except Exception as exc:                  # noqa: BLE001 - any failure here is infrastructure
                result.error = f"{type(exc).__name__}: {exc}"[:300]
                result.latency_ms = (clock() - started) * 1000
                return result
            result.latency_ms = (clock() - started) * 1000
            result.output, result.usage = out.text, out.usage
            result.cost_micro_usd = cost_or_none(out.usage, out.model, prices) if out.model else 0
            result.checks = [run_check(out.text, spec.type, spec.value) for spec in case.checks]
            if case.rubric and judge_fn is not None:
                result.judge = await judge_fn(case, out.text)
        return result

    return list(await asyncio.gather(*(one(c) for c in cases)))
