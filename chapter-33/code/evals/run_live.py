"""
Run the eval set against the REAL model. This spends money and needs ANTHROPIC_API_KEY.
Not run while writing the chapter: the SDK was not installed. Print the estimate first, run it second.

    python -m evals.run_live --cases evals/data/chat_basic.jsonl --baseline evals/baseline.json [--update-baseline]
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from ai.anthropic_client import AnthropicLLM
from ai.context import estimate_tokens
from ai.dto import ChatMessage, LLMRequest, StreamEnd, TextDelta, Usage
from ai.pricing import DEFAULT_PRICES, cost_micro_usd, format_usd
from ai.prompts import PROMPT_VERSION, SYSTEM_PROMPT

from .cases import load_cases
from .judge import judge
from .report import baseline_from_json, compare, gate, results_to_json, summarize
from .runner import GenOutput, run_eval

MODEL = os.environ.get("EVAL_MODEL", "claude-sonnet-5-5")
JUDGE_MODEL = os.environ.get("EVAL_JUDGE_MODEL", "claude-sonnet-5-5")


def estimate_cost(cases) -> int:
    """A rough upper bound BEFORE spending anything: input estimate plus a generous output allowance per case."""
    price = DEFAULT_PRICES[MODEL]
    total = Usage()
    for c in cases:
        total += Usage(input_tokens=estimate_tokens(SYSTEM_PROMPT + c.input), output_tokens=400)
        if c.rubric:
            total += Usage(input_tokens=estimate_tokens(c.input + c.rubric) + 500, output_tokens=150)
    return cost_micro_usd(total, price)


async def main(args) -> int:
    cases = load_cases(args.cases)
    print(f"{len(cases)} cases, estimated cost up to {format_usd(estimate_cost(cases))} (prompt {PROMPT_VERSION}, model {MODEL})")
    if args.dry_run:
        return 0
    client = AnthropicLLM(api_key=os.environ["ANTHROPIC_API_KEY"], timeout=60, max_retries=1)

    async def generate(case) -> GenOutput:
        msgs = tuple(ChatMessage(r, t) for r, t in case.history) + (ChatMessage("user", case.input),)
        parts, usage = [], Usage()
        async for ev in client.stream(LLMRequest(MODEL, SYSTEM_PROMPT, msgs, 1024)):
            if isinstance(ev, TextDelta):
                parts.append(ev.text)
            elif isinstance(ev, StreamEnd):
                usage = ev.usage
        return GenOutput("".join(parts), usage, MODEL)

    results = await run_eval(cases, generate, judge_fn=lambda c, t: judge(client, JUDGE_MODEL, c, t), concurrency=4)
    summary = summarize(results)
    print(f"pass {summary.pass_rate:.0%} ({summary.passed}/{summary.passed + summary.failed}), errors {summary.errors}, "
          f"cost {format_usd(summary.cost_micro_usd)}, p95 {summary.p95_latency_ms:.0f} ms")
    baseline_path = Path(args.baseline)
    comparison = compare(baseline_from_json(baseline_path.read_text()), results) if baseline_path.exists() else None
    verdict = gate(summary, comparison, min_pass_rate=args.min_pass_rate)
    for r in results:
        if r.status != "pass":
            print(f"  {r.status.upper():5} {r.case_id}: {r.error or '; '.join(r.failures)}")
    if args.update_baseline and verdict.ok:
        baseline_path.write_text(results_to_json(results))
        print("baseline updated")
    print("GATE:", "PASS" if verdict.ok else "BLOCKED")
    for reason in verdict.reasons:
        print("  -", reason)
    return 0 if verdict.ok else 1


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--cases", default="evals/data/chat_basic.jsonl")
    p.add_argument("--baseline", default="evals/baseline.json")
    p.add_argument("--min-pass-rate", type=float, default=0.9)
    p.add_argument("--update-baseline", action="store_true")
    p.add_argument("--dry-run", action="store_true", help="print the cost estimate and stop")
    sys.exit(asyncio.run(main(p.parse_args())))
