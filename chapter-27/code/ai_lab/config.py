"""Read settings from the environment. Keys never live in code (Chapter 17)."""
from __future__ import annotations

import os

DEFAULT_MODEL = "claude-sonnet-5-5"


class MissingSetting(RuntimeError):
    pass


def require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise MissingSetting(
            f"Set {name} in your environment (for example in .env, which must not be committed)."
        )
    return value


def optional(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip() or default


def default_model() -> str:
    """The model id comes from settings so you can change it without a deploy."""
    return optional("AI_DEFAULT_MODEL", DEFAULT_MODEL)
