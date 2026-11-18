"""Prompt templates: named variables, strict rendering and safe handling of untrusted data."""
import re
from dataclasses import dataclass, field

from .blocks import clean_prompt_text, wrap_untrusted

_VAR = re.compile(r"\{\{\s*([a-z][a-z0-9_]*)\s*\}\}")


class TemplateError(ValueError):
    """The template or the values given to it are wrong. Raised before any model call."""


@dataclass(frozen=True)
class Prompt:
    """What we send to a model: a system prompt and a list of messages."""

    system: str
    messages: list
    prompt_id: str = ""


@dataclass(frozen=True)
class PromptTemplate:
    """A system prompt and a user message with {{variables}}.

    untrusted: names of variables that hold text someone else wrote. They are cleaned,
    escaped and wrapped in <untrusted_data> tags, and they may only appear in the user
    message, never in the system prompt.
    """

    name: str
    system: str
    user: str
    untrusted: frozenset = field(default_factory=frozenset)
    max_chars: int = 20000  # cap for each variable

    def __post_init__(self):
        in_system = set(_VAR.findall(self.system))
        in_user = set(_VAR.findall(self.user))
        unknown = set(self.untrusted) - in_user
        if unknown:
            raise TemplateError(f"untrusted variables not used in the user message: {sorted(unknown)}")
        misplaced = set(self.untrusted) & in_system
        if misplaced:
            raise TemplateError(f"untrusted variables may not appear in the system prompt: {sorted(misplaced)}")

    @property
    def variables(self) -> frozenset:
        return frozenset(_VAR.findall(self.system)) | frozenset(_VAR.findall(self.user))

    def render(self, values: dict, *, prompt_id: str = "") -> Prompt:
        """Fill in the variables. Missing or unexpected variables are errors, not surprises."""
        missing = self.variables - set(values)
        extra = set(values) - self.variables
        if missing:
            raise TemplateError(f"Missing variables: {sorted(missing)}")
        if extra:
            raise TemplateError(f"Unknown variables (typo?): {sorted(extra)}")

        def fill(match: re.Match) -> str:
            name = match.group(1)
            text = clean_prompt_text(values[name], max_chars=self.max_chars)
            return wrap_untrusted(name, text) if name in self.untrusted else text

        # One pass: text inserted for a variable is never scanned for more {{variables}}.
        system = _VAR.sub(fill, self.system)
        user = _VAR.sub(fill, self.user)
        messages = [{"role": "user", "content": user}] if user else []
        return Prompt(system=system, messages=messages, prompt_id=prompt_id)
