"""The agent loop: a model that can call tools, with hard limits and a confirmation
gate.

Pure Python: no Django, no SDK. The model is injected (anything with a `complete()`
method), so the
loop is tested with scripted fakes and used in production with the Anthropic adapter.

The two ideas that matter most:
  * every tool_use block gets exactly one tool_result, and the history stays valid at
    every stop;
  * a CONFIRM tool never runs inside the loop. The loop pauses, the server asks the
    person, and
    only the validated arguments the server stored are ever executed.
"""
import copy
import enum
import json
import logging
from dataclasses import dataclass, field
from typing import Callable, Protocol

from .tools import ArgumentError, Risk, ToolContext, ToolError, ToolOutcome, ToolRegistry

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(self.input_tokens + other.input_tokens, self.output_tokens + other.output_tokens)

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass(frozen=True)
class ModelTurn:
    """One reply from the model, in Anthropic's content-block format:
    {"type": "text", "text": ...} and {"type": "tool_use", "id": ..., "name": ...,
    "input": {...}}."""

    content: list[dict]
    stop_reason: str
    usage: Usage = Usage()

    @property
    def text(self) -> str:
        return "".join(b.get("text", "") for b in self.content if b.get("type") == "text")

    @property
    def tool_calls(self) -> list[ToolCall]:
        return [ToolCall(b["id"], b["name"], b.get("input") or {}) for b in self.content if b.get("type") == "tool_use"]


class ModelUnavailable(Exception):
    """A ModelClient raises this for any provider failure (network, rate limit, outage),
    so callers need no SDK imports."""


class ModelClient(Protocol):
    def complete(
        self, *, system: str, messages: list[dict], tools: list[dict], on_text: Callable[[str], None] | None = None
    ) -> ModelTurn: ...


@dataclass(frozen=True)
class Limits:
    max_steps: int = 8              # model calls in one run
    max_tool_calls: int = 16        # tool calls in one run
    # checked before each model call, so the last call can overshoot a little
    max_total_tokens: int = 60_000


class Status(enum.StrEnum):
    DONE = "done"
    NEEDS_CONFIRMATION = "needs_confirmation"
    STEP_LIMIT = "step_limit"
    TOKEN_LIMIT = "token_limit"
    TRUNCATED = "truncated"


STOP_TEXT = {
    Status.STEP_LIMIT: (
        "I stopped because this needed too many steps. Check your tasks and calendar to see "
        "what was done, then try a smaller request."
    ),
    Status.TOKEN_LIMIT: "I stopped because this request used up its allowance. Try a smaller request.",
    Status.TRUNCATED: (
        "My answer was cut off, so I did not act on it. Please try again, perhaps with a "
        "shorter request."
    ),
}


@dataclass(frozen=True)
class PendingCall:
    tool_use_id: str
    tool: str
    arguments: dict   # already validated: this is what will run if the person says yes
    summary: str      # written by OUR code from those arguments, never by the model


@dataclass
class AgentResult:
    status: Status
    text: str
    messages: list[dict]
    pending: list[PendingCall] = field(default_factory=list)
    # tool_result blocks already finished in a paused turn
    results: list[dict] = field(default_factory=list)
    usage: Usage = Usage()
    steps: int = 0
    tool_calls: int = 0


@dataclass(frozen=True)
class AgentEvent:
    type: str   # text_delta | tool_started | tool_finished | confirmation_required
    data: dict


class ResumeError(ValueError):
    """The results offered to resume_agent() do not match the tool calls waiting for
    them."""


def result_block(tool_use_id: str, outcome: ToolOutcome) -> dict:
    return {"type": "tool_result", "tool_use_id": tool_use_id, "content": outcome.content, "is_error": not outcome.ok}


def _error(code: str, message: str) -> ToolOutcome:
    return ToolOutcome(False, json.dumps({"error": code, "message": message}), code)


def run_agent(
    model: ModelClient, registry: ToolRegistry, ctx: ToolContext, *, system: str, messages: list[dict],
    limits: Limits = Limits(), on_event: Callable[[AgentEvent], None] | None = None,
) -> AgentResult:
    """Run the model until it answers, hits a limit, or needs the person to confirm
    something.

    `messages` must end with the person's message. It is not modified; the new history
    is in the result.
    """
    history = copy.deepcopy(messages)
    if not history or history[-1]["role"] != "user":
        raise ValueError("The history must end with a user message.")
    return _drive(model, registry, ctx, system, history, limits, on_event)


def resume_agent(
    model: ModelClient, registry: ToolRegistry, ctx: ToolContext, *, system: str, messages: list[dict],
    results: list[dict], limits: Limits = Limits(), on_event: Callable[[AgentEvent], None] | None = None,
) -> AgentResult:
    """Continue a paused run once every waiting tool call has an outcome (executed or
    declined)."""
    history = copy.deepcopy(messages)
    if not history or history[-1]["role"] != "assistant" or not isinstance(history[-1]["content"], list):
        raise ResumeError("There is no paused tool call to resume.")
    order = [b["id"] for b in history[-1]["content"] if b.get("type") == "tool_use"]
    by_id: dict[str, dict] = {}
    for block in results:
        by_id[block["tool_use_id"]] = block
    if sorted(by_id) != sorted(order) or len(results) != len(order):
        raise ResumeError("Every tool call needs exactly one result.")
    history.append({"role": "user", "content": [by_id[i] for i in order]})
    return _drive(model, registry, ctx, system, history, limits, on_event)


def resolve_pending(
    registry: ToolRegistry, ctx: ToolContext, pending: list[PendingCall], approvals: dict[str, bool]
) -> list[dict]:
    """Turn the person's yes/no answers into tool_result blocks. Approved calls run now,
    declined ones never do."""
    blocks = []
    for call in pending:
        if call.tool_use_id not in approvals:
            raise ResumeError(f"No decision for {call.tool}.")
        if approvals[call.tool_use_id]:
            # validated again: defence in depth
            outcome = registry.execute(call.tool, call.arguments, ctx)
        else:
            outcome = ToolOutcome(True, json.dumps({"status": "declined", "message": "The person chose not to go ahead."}))
        blocks.append(result_block(call.tool_use_id, outcome))
    return blocks


def _drive(model, registry, ctx, system, history, limits, on_event) -> AgentResult:
    usage, steps, calls_made = Usage(), 0, 0

    def emit(kind: str, **data):
        if on_event:
            on_event(AgentEvent(kind, data))

    def stop(status: Status) -> AgentResult:
        text = STOP_TEXT[status]
        history.append({"role": "assistant", "content": [{"type": "text", "text": text}]})  # keeps the history valid
        return AgentResult(status, text, history, usage=usage, steps=steps, tool_calls=calls_made)

    while True:
        if steps >= limits.max_steps:
            return stop(Status.STEP_LIMIT)
        if usage.total >= limits.max_total_tokens:
            return stop(Status.TOKEN_LIMIT)

        turn = model.complete(
            system=system, messages=history, tools=registry.specs(),
            on_text=(lambda t: emit("text_delta", text=t)) if on_event else None,
        )
        steps += 1
        usage = usage + turn.usage

        if turn.stop_reason == "max_tokens":
            # a cut-off tool call may have broken arguments: never act on it
            return stop(Status.TRUNCATED)
        history.append({"role": "assistant", "content": turn.content})
        calls = turn.tool_calls
        if turn.stop_reason != "tool_use" or not calls:
            text = turn.text or "I was not able to complete that request."
            return AgentResult(Status.DONE, text, history, usage=usage, steps=steps, tool_calls=calls_made)

        results: list[dict] = []
        pending: list[PendingCall] = []
        for call in calls:
            calls_made += 1
            if calls_made > limits.max_tool_calls:
                results.append(result_block(call.id, _error("too_many_tool_calls", "Too many tool calls in one request.")))
                continue
            tool = registry.get(call.name)
            if tool is not None and tool.risk is Risk.CONFIRM:
                try:
                    clean = registry.validate(tool, call.arguments)
                    summary = tool.summarize(ctx, clean)
                except ArgumentError as exc:
                    results.append(result_block(call.id, _error("invalid_arguments", "; ".join(exc.problems))))
                except ToolError as exc:
                    results.append(result_block(call.id, _error(exc.code, str(exc))))
                except Exception:  # noqa: BLE001
                    log.exception("summarize_failed", extra={"tool": call.name})
                    results.append(result_block(call.id, _error("internal_error", "The tool failed.")))
                else:
                    pending.append(PendingCall(call.id, tool.name, clean, summary))
                    emit("confirmation_required", tool_use_id=call.id, tool=tool.name, summary=summary)
                continue
            emit("tool_started", tool=call.name)
            outcome = registry.execute(call.name, call.arguments, ctx)
            emit("tool_finished", tool=call.name, ok=outcome.ok, code=outcome.code)
            results.append(result_block(call.id, outcome))

        if pending:
            return AgentResult(Status.NEEDS_CONFIRMATION, turn.text, history, pending, results,
                               usage=usage, steps=steps, tool_calls=calls_made)
        history.append({"role": "user", "content": results})
