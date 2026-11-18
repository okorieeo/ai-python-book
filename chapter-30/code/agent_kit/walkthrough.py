"""A scripted run, offline. No API key and no network.   python -m agent_kit.walkthrough

The "model" here is a fake that replays fixed replies, so you can watch the loop,
the tools, the approval pause and the resume without spending anything. The agent
code, the tools and the SDK are the real ones.
"""
from __future__ import annotations

import sys

from .agent import Agent
from .demo import SYSTEM, seed
from .demo_app import build_registry
from .fake_api import FakeAPI, message, text, tool_turn
from .state import RunState
from .tools import ToolContext
from .trace import describe_messages

REQUEST = "Rename my egg chat to Egg report, and delete my feed chat."


def scripted_replies() -> list[dict]:
    return [
        tool_turn(("toolu_1", "list_conversations", {}), in_tokens=420, out_tokens=40),
        tool_turn(
            ("toolu_2", "rename_conversation", {"conversation_id": 1, "new_title": "Egg report"}),
            ("toolu_3", "delete_conversation", {"conversation_id": 2}),
            in_tokens=610, out_tokens=70,
        ),
        message([text("All done. Your egg chat is now 'Egg report'. The feed chat was handled as you decided.")],
                in_tokens=760, out_tokens=35),
    ]


def main(argv=None) -> int:
    decline = "--decline" in (argv if argv is not None else sys.argv[1:])
    store = seed()
    api = FakeAPI(scripted_replies())
    agent = Agent(api.client, model="claude-sonnet-5-5", registry=build_registry(), system=SYSTEM)
    ctx = ToolContext(user_id=1, role="member", services=store)

    print(f"user: {REQUEST}\n")
    result = agent.start([{"role": "user", "content": REQUEST}], ctx)
    print(f"REQUEST 1 ended with status: {result.status}")
    for call in result.state.pending:
        print(f"  waiting for approval: {call.name} {call.input}")
    saved = result.state.to_json()  # in a web app this goes into your database
    print(f"  run state saved ({len(saved):,} bytes of JSON). Nothing has been deleted yet: "
          f"conversation 2 exists = {store.exists(2)}\n")

    restored = RunState.from_json(saved)  # a later request loads it back
    decisions = {c.tool_use_id: (not decline) for c in restored.pending}
    print(f"REQUEST 2: the user clicks {'Decline' if decline else 'Approve'}")
    result = agent.resume(restored, decisions, ctx)
    print(f"  status: {result.status} | conversation 2 exists = {store.exists(2)} | "
          f"conversation 1 title = {store.get_for(1, 1).title!r}\n")

    print("TRANSCRIPT")
    for line in describe_messages(result.state.messages):
        print("  " + line)
    s = result.state
    print(f"\nmodel calls: {s.steps} | tool calls: {s.tool_calls} | tokens in={s.usage.input_tokens} "
          f"out={s.usage.output_tokens} | cost ${s.cost_usd:.6f}")
    print("audit: " + ", ".join(f"{a.tool}:{a.status}" for a in s.audit))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
