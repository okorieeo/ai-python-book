"""Tools: what the model is allowed to ask your app to do.

A tool is a name, a description the model reads, a JSON Schema for its inputs,
a Python handler that does the work, and a risk level that decides whether a
human must approve each call.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Optional

import jsonschema

NAME_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")  # the rule in Anthropic's tool docs
RISKS = ("read", "write", "destructive")
MIN_DESCRIPTION_CHARS = 40


class ToolError(Exception):
    """Raise this inside a handler for a problem the MODEL should see.

    The message is sent to the model, so keep it short, useful and free of
    secrets, for example "Conversation 42 was not found."
    """


@dataclass(frozen=True)
class ToolContext:
    """Who is asking, and how to reach your data. Built per request, never shared."""

    user_id: int
    role: str = "member"
    services: Any = None  # your service layer (Chapter 29); handlers use it, not global state


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    input_schema: dict
    handler: Callable[[dict, ToolContext], Any]
    risk: str = "read"  # "read", "write" or "destructive"
    strict: bool = False  # ask Claude to guarantee schema-valid inputs

    def __post_init__(self) -> None:
        if not NAME_RE.match(self.name):
            raise ValueError(f"Tool name {self.name!r} must match {NAME_RE.pattern}")
        if self.risk not in RISKS:
            raise ValueError(f"risk must be one of {RISKS}, got {self.risk!r}")
        if len(self.description.strip()) < MIN_DESCRIPTION_CHARS:
            raise ValueError(
                f"Tool {self.name!r}: write a real description (at least "
                f"{MIN_DESCRIPTION_CHARS} characters). The model decides from it."
            )
        if self.input_schema.get("type") != "object":
            raise ValueError(f"Tool {self.name!r}: input_schema must have type 'object'")
        jsonschema.Draft202012Validator.check_schema(self.input_schema)  # raises if invalid
        if self.strict and self.input_schema.get("additionalProperties") is not False:
            raise ValueError(
                f"Tool {self.name!r}: strict tools need additionalProperties set to false"
            )

    def definition(self) -> dict:
        """The dict you pass in the `tools` parameter of the API request."""
        d: dict[str, Any] = {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }
        if self.strict:
            d["strict"] = True
        return d

    def validate(self, args: Any) -> list[str]:
        """Return readable problems with the model's arguments, or an empty list."""
        if not isinstance(args, dict):
            return ["the input must be a JSON object"]
        validator = jsonschema.Draft202012Validator(self.input_schema)
        problems = []
        for err in sorted(validator.iter_errors(args), key=lambda e: list(e.absolute_path)):
            where = ".".join(str(p) for p in err.absolute_path) or "input"
            problems.append(f"{where}: {err.message}")
        return problems


class ToolRegistry:
    def __init__(self, tools: Iterable[Tool] = ()) -> None:
        self._tools: dict[str, Tool] = {}
        for t in tools:
            self.register(t)

    def register(self, tool: Tool) -> Tool:
        if tool.name in self._tools:
            raise ValueError(f"Tool {tool.name!r} is already registered")
        self._tools[tool.name] = tool
        return tool

    def get(self, name: str) -> Optional[Tool]:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return sorted(self._tools)

    def definitions(self, allowed: Optional[Iterable[str]] = None) -> list[dict]:
        """Definitions to send to the model. Pass `allowed` to hide tools from a user."""
        allow = None if allowed is None else set(allowed)
        return [t.definition() for n, t in self._tools.items() if allow is None or n in allow]
