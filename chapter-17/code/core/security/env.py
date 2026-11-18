"""Reading secrets: from an environment variable, or from a file (Docker style)."""
import os
from pathlib import Path


class MissingSecret(RuntimeError):
    """A required secret is not configured."""


def env_or_file(
    name: str, default: str | None = None, environ=os.environ
) -> str | None:
    """Return $NAME, or the contents of the file named by $NAME_FILE (which wins)."""
    file_path = environ.get(f"{name}_FILE")
    if file_path:
        return Path(file_path).read_text(encoding="utf-8").strip()
    return environ.get(name, default)


def require_secret(name: str, environ=os.environ) -> str:
    value = env_or_file(name, environ=environ)
    if not value:
        raise MissingSecret(f"Set {name} (or {name}_FILE). See .env.example.")
    return value


class Secret:
    """Wraps a secret so printing, logging or f-strings show *** not the value."""

    __slots__ = ("_value",)

    def __init__(self, value: str):
        self._value = value

    def reveal(self) -> str:
        return self._value

    def __repr__(self) -> str:
        return "Secret('***')"

    __str__ = __repr__
