"""Try the agent in a terminal.   python -m agent_kit.demo "Rename my egg chat to Egg report"

Needs ANTHROPIC_API_KEY. It runs against an in-memory demo store, asks you to
approve destructive actions in the terminal, and prints every step.
"""
from __future__ import annotations

import argparse
import sys

from ai_lab import config

from .agent import Agent
from .demo_app import ChatStore, build_registry, policy_for_role
from .tools import ToolContext

SYSTEM = (
    "You are the assistant inside a chat app. You can look up and manage the current user's "
    "conversations with the tools provided. Look things up before changing them, keep answers "
    "short, and never claim to have done something unless a tool result says so."
)


def seed() -> ChatStore:
    store = ChatStore()
    store.add(1, "Egg production", ["Eggs dropped 12% last week", "Check the feed supplier"])
    store.add(1, "Feed prices", ["Maize is up again", "Ask about bulk discount"])
    store.add(2, "Someone else's private chat", ["Not yours"])
    return store


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("request")
    p.add_argument("--role", choices=["member", "viewer"], default="member")
    p.add_argument("--model", default=config.default_model())
    args = p.parse_args(argv)
    try:
        config.require("ANTHROPIC_API_KEY")
    except config.MissingSetting as exc:
        print(f"Configuration problem: {exc}", file=sys.stderr)
        return 2
    import anthropic

    store = seed()
    ctx = ToolContext(user_id=1, role=args.role, services=store)
    agent = Agent(
        anthropic.Anthropic(), model=args.model, registry=build_registry(),
        policy=policy_for_role(args.role), system=SYSTEM,
    )
    result = agent.start([{"role": "user", "content": args.request}], ctx)
    while result.status == "needs_approval":
        if result.text:
            print(f"assistant: {result.text}")
        decisions = {}
        for call in result.state.pending:
            answer = input(f"Approve {call.name} {call.input}? [y/N] ").strip().lower()
            decisions[call.tool_use_id] = answer == "y"
        result = agent.resume(result.state, decisions, ctx)
    print(f"\nassistant: {result.text or '(no text)'}")
    s = result.state
    print(f"--- status={result.status} {result.stop_reason} | steps={s.steps} tool_calls={s.tool_calls} "
          f"| tokens in={s.usage.prompt_tokens:,} out={s.usage.output_tokens:,} | cost ${s.cost_usd:.6f}")
    for a in s.audit:
        print(f"    tool {a.tool:<22} {a.status:<14} args={a.arg_names}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
