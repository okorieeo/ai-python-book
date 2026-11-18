"""Tools the assistant may call: definitions, argument validation and safe execution.
Pure Python, no Django.

A tool is a plain function plus three promises we make to the model and to ourselves:
  1. a JSON schema that says exactly which arguments exist (the model reads it; we
  ENFORCE it);
  2. a risk level that decides whether the app may run it alone or must ask the person
  first;
  3. the identity (ToolContext.user) comes from the server, never from the model's
  arguments.
"""
import enum
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Iterable
from zoneinfo import ZoneInfo

from .untrusted import to_model_json

log = logging.getLogger(__name__)

MAX_RESULT_CHARS = 12_000
_TOOL_NAME = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


class Risk(enum.StrEnum):
    READ = "read"        # looks things up; nothing changes
    # changes data in a way that is easy to see and undo; runs without asking
    WRITE = "write"
    # hard to undo or high impact; the app asks the person before it runs
    CONFIRM = "confirm"


class ToolError(Exception):
    """Raised by a handler for a problem the MODEL can fix (not found, bad time, clash).
    The message goes back to it."""

    def __init__(self, message: str, code: str = "invalid"):
        super().__init__(message)
        self.code = code


class ArgumentError(ValueError):
    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


@dataclass(frozen=True)
class ToolContext:
    """Who is asking, and when. Set by the server for every call. The model cannot
    change either."""

    user: Any
    now: datetime        # aware, UTC
    tz: ZoneInfo         # the user's own time zone
    request: Any = None  # the HTTP request or WebSocket scope, for audit records


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    input_schema: dict
    handler: Callable[[ToolContext, dict], dict]
    risk: Risk = Risk.READ
    # plain-language "what will happen" for CONFIRM tools
    summarize: Callable[[ToolContext, dict], str] | None = None


@dataclass(frozen=True)
class ToolOutcome:
    ok: bool
    content: str   # JSON text: this is what the model reads
    code: str = ""


def _fail(code: str, message: str, **extra) -> ToolOutcome:
    return ToolOutcome(False, json.dumps({"error": code, "message": message, **extra}), code)


_TYPES = {
    "string": lambda v: isinstance(v, str),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "array": lambda v: isinstance(v, list),
    "object": lambda v: isinstance(v, dict),
}


def validate_arguments(schema: dict, arguments: Any) -> dict:
    """Check model-produced arguments against the small JSON-schema subset our tools
    use; return a clean copy.

    Strict on purpose: unknown fields are errors, "5" is not 5, True is not 1. Supports
    type, enum,
    minLength, maxLength, minimum, maximum, pattern, maxItems, items, required and
    default.
    Production alternative: the `jsonschema` package. We keep this ~40 lines so the same
    schema
    that is sent to the model is the one that checks its answer, with nothing hidden.
    """
    if not isinstance(arguments, dict):
        raise ArgumentError(["arguments must be an object"])
    properties = schema.get("properties", {})
    problems: list[str] = []
    for name in arguments:
        if name not in properties:
            problems.append(f"{name}: unknown field")
    clean: dict = {}
    for name, spec in properties.items():
        if name not in arguments:
            if name in schema.get("required", []):
                problems.append(f"{name}: is required")
            elif "default" in spec:
                clean[name] = spec["default"]
            continue
        value = arguments[name]
        if not _TYPES[spec["type"]](value):
            problems.append(f"{name}: must be of type {spec['type']}")
            continue
        if "enum" in spec and value not in spec["enum"]:
            problems.append(f"{name}: must be one of {', '.join(map(str, spec['enum']))}")
        if isinstance(value, str):
            if "minLength" in spec and len(value) < spec["minLength"]:
                problems.append(f"{name}: must have at least {spec['minLength']} characters")
            if "maxLength" in spec and len(value) > spec["maxLength"]:
                problems.append(f"{name}: must have at most {spec['maxLength']} characters")
            if "pattern" in spec and not re.fullmatch(spec["pattern"], value):
                problems.append(f"{name}: has the wrong format")
        if spec["type"] in ("integer", "number"):
            if "minimum" in spec and value < spec["minimum"]:
                problems.append(f"{name}: must be at least {spec['minimum']}")
            if "maximum" in spec and value > spec["maximum"]:
                problems.append(f"{name}: must be at most {spec['maximum']}")
        if spec["type"] == "array":
            if "maxItems" in spec and len(value) > spec["maxItems"]:
                problems.append(f"{name}: at most {spec['maxItems']} items")
            item_type = spec.get("items", {}).get("type")
            if item_type and not all(_TYPES[item_type](v) for v in value):
                problems.append(f"{name}: every item must be of type {item_type}")
        clean[name] = value
    if problems:
        raise ArgumentError(problems)
    return clean


class ToolRegistry:
    def __init__(self, tools: Iterable[Tool], *, free_text: dict[str, int] | None = None):
        """`free_text` names the result fields that hold text written by people
        ("title": 200, "notes": 500).
        Every tool result is scanned for them and wrapped as untrusted data, so a new
        tool cannot forget to."""
        self.free_text = dict(free_text or {})
        self._tools: dict[str, Tool] = {}
        for tool in tools:
            if not _TOOL_NAME.match(tool.name):
                raise ValueError(f"Invalid tool name: {tool.name!r}")
            if tool.name in self._tools:
                raise ValueError(f"Duplicate tool name: {tool.name}")
            if tool.risk is Risk.CONFIRM and tool.summarize is None:
                raise ValueError(f"{tool.name}: a CONFIRM tool must say what it will do (summarize=...)")
            self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def tools(self) -> list[Tool]:
        return list(self._tools.values())

    def names(self) -> list[str]:
        return sorted(self._tools)

    def specs(self) -> list[dict]:
        """The `tools` list in the shape the Anthropic Messages API expects."""
        return [
            {"name": t.name, "description": t.description, "input_schema": t.input_schema}
            for t in self._tools.values()
        ]

    def validate(self, tool: Tool, arguments: Any) -> dict:
        return validate_arguments(tool.input_schema, arguments)

    def execute(self, name: str, arguments: Any, ctx: ToolContext) -> ToolOutcome:
        """Validate, run and package one tool call. Never raises: the model always gets
        a readable answer."""
        tool = self.get(name)
        if tool is None:
            return _fail("unknown_tool", f"There is no tool called {name!r}.", available=self.names())
        try:
            clean = self.validate(tool, arguments)
        except ArgumentError as exc:
            return _fail("invalid_arguments", "Fix these problems and try again.", problems=exc.problems)
        try:
            result = tool.handler(ctx, clean)
            text = to_model_json(result, free_text=self.free_text)
        except ToolError as exc:
            return _fail(exc.code, str(exc))
        # noqa: BLE001 - a tool bug must not crash the conversation or leak a stack
        # trace
        except Exception:
            log.exception("tool_failed", extra={"tool": name})
            return _fail("internal_error", "The tool failed. Tell the user something went wrong; do not retry.")
        if len(text) > MAX_RESULT_CHARS:
            return _fail("result_too_large", "Too much data. Ask for fewer items or a narrower date range.")
        return ToolOutcome(True, text)
