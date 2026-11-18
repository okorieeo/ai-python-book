"""The agent loop: call the model, run the tools it asks for, repeat.

An agent is a while loop around a model call. The model never runs anything.
It asks (a tool_use block), your code decides, and your code replies with the
result (a tool_result block). Every safety property lives in this file and in
tools.py, not in the prompt.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

from ai_lab.catalog import get_model
from ai_lab.cost import TokenUsage, cost_usd

from .policy import Policy
from .state import AuditRecord, PendingCall, RunResult, RunState
from .tools import Tool, ToolContext, ToolError, ToolRegistry

log = logging.getLogger("agent_kit")


def result_block(tool_use_id: str, content: str, *, error: bool = False) -> dict:
    block = {"type": "tool_result", "tool_use_id": tool_use_id, "content": content}
    if error:
        block["is_error"] = True
    return block


class Agent:
    def __init__(
        self,
        client: Any,
        *,
        model: str,
        registry: ToolRegistry,
        policy: Optional[Policy] = None,
        system: Optional[str] = None,
        max_tokens: int = 2048,
        effort: Optional[str] = None,
        tool_choice: Optional[dict] = None,
    ) -> None:
        self.client = client
        self.model = model
        # Fail early if the model is not in the catalog: the budget needs its prices.
        self.model_info = get_model(model)
        self.registry = registry
        self.policy = policy or Policy()
        self.system = system
        self.max_tokens = max_tokens
        self.effort = effort
        # Claude Opus 5.5 and Fable 5.1 reject tool_choice types "any" and "tool".
        self.tool_choice = tool_choice

    # ------------------------------------------------------------------ public
    def start(self, messages: list[dict], ctx: ToolContext) -> RunResult:
        """Run on a conversation whose last message is the user's new message."""
        if not messages or messages[-1].get("role") != "user":
            raise ValueError("The last message must come from the user.")
        return self._drive(RunState(messages=[dict(m) for m in messages]), ctx)

    def resume(self, state: RunState, decisions: dict[str, bool], ctx: ToolContext) -> RunResult:
        """Continue a paused run. `decisions` maps tool_use_id to approve (True) or decline.

        Anything the human did not explicitly approve is declined: fail closed.
        """
        if not state.pending:
            raise ValueError("This run has nothing waiting for approval.")
        pending_ids = {p.tool_use_id for p in state.pending}
        unknown = set(decisions) - pending_ids
        if unknown:
            raise ValueError(f"Decisions for unknown tool calls: {sorted(unknown)}")
        calls, state.pending = state.pending, []
        for call in calls:
            if decisions.get(call.tool_use_id) is True:
                # Run every check again. Time has passed; permissions may have changed.
                self._handle(call.tool_use_id, call.name, call.input, ctx, state, approved=True)
            else:
                state.results[call.tool_use_id] = result_block(
                    call.tool_use_id,
                    "The user declined this action. Do not retry it. "
                    "Ask what they would like to do instead.",
                    error=True,
                )
                state.audit.append(AuditRecord(call.name, "declined", sorted(call.input)))
        self._append_results(state)
        return self._drive(state, ctx)

    # ---------------------------------------------------------------- the loop
    def _drive(self, state: RunState, ctx: ToolContext) -> RunResult:
        while True:
            if state.steps >= self.policy.max_steps:
                return RunResult("stopped", "", state, "max_steps")
            if state.cost_usd >= self.policy.max_cost_usd:
                return RunResult("stopped", "", state, "budget")

            response = self._call(state)
            state.steps += 1
            usage = TokenUsage.from_anthropic(response.usage)
            state.usage = state.usage + usage
            state.cost_usd += cost_usd(self.model_info, usage)

            # Echo the assistant's content back exactly as received (thinking blocks included).
            state.messages.append(
                {
                    "role": "assistant",
                    "content": [b.model_dump(mode="json", exclude_none=True) for b in response.content],
                }
            )
            text = "".join(b.text for b in response.content if b.type == "text")
            reason = str(response.stop_reason)

            if reason == "end_turn":
                return RunResult("completed", text, state)
            if reason != "tool_use":
                why = "truncated" if reason == "max_tokens" else f"unexpected:{reason}"
                return RunResult("stopped", text, state, why)

            tool_uses = [b for b in response.content if b.type == "tool_use"]
            if state.tool_calls + len(tool_uses) > self.policy.max_tool_calls:
                return RunResult("stopped", text, state, "max_tool_calls")

            state.order = [t.id for t in tool_uses]
            state.results = {}
            state.pending = []
            for tu in tool_uses:
                state.tool_calls += 1
                self._handle(tu.id, tu.name, tu.input, ctx, state, approved=False)

            if state.pending:
                return RunResult("needs_approval", text, state)
            self._append_results(state)

    # ------------------------------------------------------------ one tool call
    def _handle(
        self, tool_use_id: str, name: str, args: Any, ctx: ToolContext, state: RunState, *, approved: bool
    ) -> None:
        names = sorted(args) if isinstance(args, dict) else []
        tool = self.registry.get(name)
        if tool is None:
            available = ", ".join(self._visible_names())
            state.results[tool_use_id] = result_block(
                tool_use_id, f"Unknown tool {name!r}. Available tools: {available}.", error=True
            )
            state.audit.append(AuditRecord(name, "unknown", names))
            return
        if not self.policy.allows(tool):
            state.results[tool_use_id] = result_block(
                tool_use_id, "You are not permitted to use this tool.", error=True
            )
            state.audit.append(AuditRecord(name, "not_permitted", names))
            return
        problems = tool.validate(args)
        if problems:
            state.results[tool_use_id] = result_block(
                tool_use_id, "Invalid input: " + "; ".join(problems), error=True
            )
            state.audit.append(AuditRecord(name, "invalid", names))
            return
        if self.policy.needs_approval(tool) and not approved:
            state.pending.append(PendingCall(tool_use_id, name, args))
            state.audit.append(AuditRecord(name, "pending", names))
            return
        state.results[tool_use_id] = self._execute(tool, tool_use_id, args, ctx, state)

    def _execute(self, tool: Tool, tool_use_id: str, args: dict, ctx: ToolContext, state: RunState) -> dict:
        names = sorted(args)
        try:
            raw = tool.handler(args, ctx)
        except ToolError as exc:
            state.audit.append(AuditRecord(tool.name, "error", names))
            return result_block(tool_use_id, str(exc), error=True)
        except Exception as exc:  # a bug in your handler must not crash the run or leak details
            log.error("tool %s failed with %s", tool.name, type(exc).__name__)
            state.audit.append(AuditRecord(tool.name, "error", names))
            return result_block(tool_use_id, "The tool failed unexpectedly.", error=True)
        text = raw if isinstance(raw, str) else json.dumps(raw, default=str)
        limit = self.policy.max_result_chars
        if len(text) > limit:
            text = text[:limit] + f"\n[truncated: {len(text) - limit} more characters]"
        state.audit.append(AuditRecord(tool.name, "ok", names, len(text)))
        return result_block(tool_use_id, text)

    # ---------------------------------------------------------------- plumbing
    def _visible_names(self) -> list[str]:
        return [n for n in self.registry.names() if self.policy.allows(self.registry.get(n))]

    def _append_results(self, state: RunState) -> None:
        missing = [i for i in state.order if i not in state.results]
        if missing:
            raise RuntimeError(f"No result for tool calls {missing}")
        # One user message, tool_result blocks only, in the same order as the tool_use blocks.
        state.messages.append({"role": "user", "content": [state.results[i] for i in state.order]})

    def _call(self, state: RunState) -> Any:
        params: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": state.messages,
        }
        tools = self.registry.definitions(self.policy.allowed_tools)
        if tools:
            params["tools"] = tools
        if self.system:
            params["system"] = self.system
        if self.effort:
            params["output_config"] = {"effort": self.effort}
        if self.tool_choice:
            params["tool_choice"] = self.tool_choice
        return self.client.messages.create(**params)
