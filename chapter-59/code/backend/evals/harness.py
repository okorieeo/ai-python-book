"""Tool-use evaluations. Pure Python, no Django.

A unit test proves OUR code is right. An eval measures whether the MODEL chooses the
right tools with the right
arguments. We run the real tool definitions (so the schemas the model sees are the
production ones) but swap the
handlers for stubs that return canned data, so no database is needed and every run
starts from the same world.
"""
import json
from dataclasses import dataclass, field, replace
from typing import Callable

from assistant.agent import Limits, ModelClient, run_agent
from assistant.prompt import build_system_prompt, stamp_user_message
from assistant.tools import ToolContext, ToolRegistry


@dataclass(frozen=True)
class Expect:
    tool: str
    # each value is an exact match, or a predicate taking the argument
    args: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Case:
    name: str
    message: str
    # these calls must happen, in this order (other calls may happen between)
    expect: tuple[Expect, ...]
    forbid: tuple[str, ...] = ()               # these tools must never be called
    # tool name -> the stub's answer for this case
    canned: dict = field(default_factory=dict)


@dataclass
class CaseResult:
    case: Case
    passed: bool
    calls: list[tuple[str, dict]]
    problems: list[str]


def stub_registry(real: ToolRegistry, calls: list, canned: dict) -> ToolRegistry:
    """Same names, descriptions, schemas and risk levels as production; handlers that
    record and answer from `canned`."""
    def stub(name):
        def handler(ctx, args):
            calls.append((name, dict(args)))
            return canned.get(name, {"ok": True})
        return handler

    return ToolRegistry(
        [replace(t, handler=stub(t.name), summarize=(lambda ctx, a: "stub") if t.summarize else None) for t in real.tools()],
        free_text=real.free_text,
    )


def _matches(expected, actual) -> bool:
    return expected(actual) if callable(expected) else expected == actual


def judge(case: Case, calls: list[tuple[str, dict]]) -> list[str]:
    problems = [f"called forbidden tool {n}" for n, _ in calls if n in case.forbid]
    cursor = 0
    for want in case.expect:
        for i in range(cursor, len(calls)):
            name, args = calls[i]
            if name == want.tool and all(k in args and _matches(v, args[k]) for k, v in want.args.items()):
                cursor = i + 1
                break
        else:
            problems.append(f"expected {want.tool} with {sorted(want.args)}")
    return problems


def run_case(case: Case, *, model: ModelClient, real_registry: ToolRegistry, ctx: ToolContext) -> CaseResult:
    calls: list[tuple[str, dict]] = []
    registry = stub_registry(real_registry, calls, case.canned)
    system = build_system_prompt(tz_name=ctx.tz.key, today=ctx.now.astimezone(ctx.tz).date())
    messages = [{"role": "user", "content": stamp_user_message(case.message, now=ctx.now, tz=ctx.tz)}]
    run_agent(model, registry, ctx, system=system, messages=messages, limits=Limits(max_steps=6))
    problems = judge(case, calls)
    return CaseResult(case, not problems, calls, problems)


def run_all(cases, *, model: ModelClient, real_registry: ToolRegistry, ctx: ToolContext,
            report: Callable[[str], None] = print) -> list[CaseResult]:
    results = [run_case(c, model=model, real_registry=real_registry, ctx=ctx) for c in cases]
    for r in results:
        report(f"{'PASS' if r.passed else 'FAIL'}  {r.case.name}" + ("" if r.passed else f"  -> {'; '.join(r.problems)}"))
    report(f"{sum(r.passed for r in results)}/{len(results)} passed")
    return results
