"""Run state: everything needed to pause an agent run and resume it later.

A web request cannot wait minutes for a human to click Approve. So when a tool
needs approval, the run stops, its state is saved (as JSON, in your database),
the user sees a confirmation card, and a later request resumes the run.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

from ai_lab.cost import TokenUsage


@dataclass
class PendingCall:
    tool_use_id: str
    name: str
    input: dict


@dataclass
class AuditRecord:
    """What we log about a tool call. Argument NAMES only, never the values (Chapter 17)."""

    tool: str
    status: str  # ok, error, invalid, unknown, not_permitted, pending, approved, declined
    arg_names: list[str]
    result_chars: int = 0


@dataclass
class RunState:
    messages: list[dict]
    order: list[str] = field(default_factory=list)  # tool_use ids of the latest assistant turn
    results: dict[str, dict] = field(default_factory=dict)  # tool_use_id -> tool_result block
    pending: list[PendingCall] = field(default_factory=list)
    steps: int = 0
    tool_calls: int = 0
    usage: TokenUsage = field(default_factory=TokenUsage)
    cost_usd: float = 0.0
    audit: list[AuditRecord] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, raw: str) -> "RunState":
        d: dict[str, Any] = json.loads(raw)
        return cls(
            messages=d["messages"],
            order=d["order"],
            results=d["results"],
            pending=[PendingCall(**p) for p in d["pending"]],
            steps=d["steps"],
            tool_calls=d["tool_calls"],
            usage=TokenUsage(**d["usage"]),
            cost_usd=d["cost_usd"],
            audit=[AuditRecord(**a) for a in d["audit"]],
        )


@dataclass
class RunResult:
    status: str  # "completed", "needs_approval" or "stopped"
    text: str  # the assistant's words to show the user
    state: RunState
    stop_reason: str = ""  # why a run stopped: max_steps, budget, truncated, ...
