"""Policy: the limits and rules around one agent run."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .tools import Tool


@dataclass(frozen=True)
class Policy:
    # Which tools this user may use. None means every registered tool.
    allowed_tools: Optional[frozenset[str]] = None
    max_steps: int = 8  # model calls in one run
    max_tool_calls: int = 20  # tool executions in one run
    max_cost_usd: float = 0.50  # stop the run when it has cost this much
    max_result_chars: int = 8_000  # cut tool output so it cannot flood the context
    # Risk levels that must be approved by a human before the tool runs.
    approval_for: frozenset[str] = frozenset({"destructive"})

    def allows(self, tool: Tool) -> bool:
        return self.allowed_tools is None or tool.name in self.allowed_tools

    def needs_approval(self, tool: Tool) -> bool:
        return tool.risk in self.approval_for
