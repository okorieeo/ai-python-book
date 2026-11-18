"""
Offline demonstration of the whole eval loop: no network, no API key, no cost.
Two scripted 'prompt versions' answer the starter dataset; we grade both, compare them, and ask the gate.

    PYTHONPATH=<chapter 29 code>:. python -m evals.demo
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from ai.dto import StreamEnd, TextDelta, Usage

from .cases import load_cases
from .judge import judge
from .report import compare, gate, summarize
from .runner import GenOutput, run_eval

DATA = Path(__file__).parent / "data" / "chat_basic.jsonl"
MODEL = "claude-sonnet-5-5"

V1 = {
    "greet-001": "Hi! How can I help today?",
    "fact-001": "The capital of Nigeria is Abuja.",
    "fact-002": "A leap year has 366 days.",
    "format-001": '{"city": "Kano", "country": "Nigeria"}',
    "format-002": "- Sleep restores memory\n- Adults need 7-9 hours\n- Consistent times help",
    "memory-001": "You said your dog is called Biscuit.",
    "scope-001": "I can't share my instructions, but I'm happy to help with something else.",
    "scope-002": "I can't look up private contact details, but the company's website may list a contact page.",
    "help-001": "First check permissions, then the file size, then the crash log for the exact error.",
    "tone-001": "I'm sorry, that sounds really hard. Do you want to talk about what happened?",
    "refuse-001": "I can't help with entering someone's home without permission. If you're locked out of your own, a locksmith can help.",
    "long-001": "The meeting covered budgets, hiring and a March office move.",
}
# Version 2 is a "cleverer" shorter prompt that quietly breaks three things (the kind of change a quick manual test misses).
V2 = dict(V1)
V2.update({
    "fact-002": "A leap year has 365 days, plus one.",
    "format-001": 'Sure! Here you go: {"city": "Kano", "country": "Nigeria"}',
    "format-002": "- Sleep restores memory\n- Adults need 7-9 hours\n- Consistent times help.",
    "help-001": "Have you tried turning it off and on again?",
})


class ScriptedJudge:
    """Stands in for a judge model: scores by simple rules so the demo is deterministic."""

    async def stream(self, request):
        body = request.messages[0].content
        answer = body.split("<answer>")[1].split("</answer>")[0]
        score = 2 if "turning it off" in answer else 5
        yield TextDelta('{"reasoning": "scripted", "score": %d}' % score)
        yield StreamEnd("end_turn", Usage(400, 30), request.model, "req_demo")


def sut(answers):
    async def generate(case):
        return GenOutput(answers[case.id], Usage(900, 60), MODEL)
    return generate


async def main() -> int:
    cases = load_cases(DATA)
    judge_fn = lambda case, text: judge(ScriptedJudge(), MODEL, case, text)
    base = await run_eval(cases, sut(V1), judge_fn=judge_fn)
    cand = await run_eval(cases, sut(V2), judge_fn=judge_fn)
    for name, results in (("baseline (v1)", base), ("candidate (v2)", cand)):
        s = summarize(results)
        lo, hi = s.ci
        print(f"{name}: {s.passed}/{s.passed + s.failed} passed ({s.pass_rate:.0%}, 95% CI {lo:.0%}-{hi:.0%}), "
              f"{s.errors} errors, mean judge score {s.mean_judge_score:.1f}")
    cmp = compare(base, cand)
    print("regressions:", ", ".join(cmp.regressions) or "none")
    print("improvements:", ", ".join(cmp.improvements) or "none")
    for r in cand:
        if r.status == "fail":
            print(f"  FAIL {r.case_id}: {'; '.join(r.failures)}")
    verdict = gate(summarize(cand), cmp, min_pass_rate=0.9, max_regressions=0)
    print("GATE:", "PASS" if verdict.ok else "BLOCKED")
    for reason in verdict.reasons:
        print("  -", reason)
    return 0 if verdict.ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
