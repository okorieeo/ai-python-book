"""Run the evaluation cases against the REAL model. Costs a few cents. Not run while writing Chapter 59.

    cd backend
    DJANGO_SETTINGS_MODULE=config.settings ANTHROPIC_API_KEY=... python -m evals.run_live --repeat 3

Models are not deterministic, so each case runs several times; read the pass RATE, not a single result.
"""
import argparse
from datetime import datetime

import django

django.setup()

from assistant.anthropic_client import AnthropicClient  # noqa: E402
from assistant.tools import ToolContext  # noqa: E402
from assistant.toolset import build_registry  # noqa: E402
from core.timeutils import UTC, get_zone  # noqa: E402
from evals.cases import CASES  # noqa: E402
from evals.harness import run_case  # noqa: E402

# "Now" is fixed so the expected dates in cases.py stay correct: 10:00 on Wed 11 Nov 2026 in Lagos.
CTX = ToolContext(user=None, now=datetime(2026, 11, 11, 9, 0, tzinfo=UTC), tz=get_zone("Africa/Lagos"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeat", type=int, default=3)
    repeat = parser.parse_args().repeat
    model, registry = AnthropicClient(), build_registry()
    total = passed = 0
    for case in CASES:
        results = [run_case(case, model=model, real_registry=registry, ctx=CTX) for _ in range(repeat)]
        wins = sum(r.passed for r in results)
        total, passed = total + repeat, passed + wins
        problems = sorted({p for r in results for p in r.problems})
        print(f"{wins}/{repeat}  {case.name}" + (f"   <- {'; '.join(problems)}" if problems else ""))
    print(f"\n{passed}/{total} runs passed ({100 * passed // total}%) with {model.model}")


if __name__ == "__main__":
    main()
