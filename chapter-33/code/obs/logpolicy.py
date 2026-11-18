"""
When may the CONTENT of a conversation reach the logs? Metadata (ids, status, token counts, cost, timings)
is always fine. Content is a decision with four settings, and production never gets 'all'.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from evals.rollout import in_rollout

from .scrub import scrub_pii

MODES = ("off", "errors", "sampled", "all")
BAD_STATUSES = {"failed", "interrupted", "refused", "truncated"}


@dataclass(frozen=True)
class ContentLogPolicy:
    mode: str = "off"
    sample_percent: float = 1.0
    max_chars: int = 2000
    environment: str = "production"
    salt: str = "content-log"

    def __post_init__(self):
        if self.mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}")
        if self.mode == "all" and self.environment == "production":
            raise ValueError("logging all conversation content is not allowed in production")
        if not 0 <= self.sample_percent <= 100:
            raise ValueError("sample_percent must be between 0 and 100")


def should_log_content(policy: ContentLogPolicy, *, status: str, message_id: int | str) -> bool:
    if policy.mode == "off":
        return False
    if policy.mode == "all":
        return True
    if status in BAD_STATUSES:
        return True                       # 'errors' and 'sampled' both keep what went wrong
    if policy.mode == "sampled":
        return in_rollout(message_id, policy.sample_percent, policy.salt)
    return False


def prepare_content(text: str, policy: ContentLogPolicy, redact: Callable[[str], str] | None = None) -> str:
    """Secrets out (Chapter 17's redact), personal patterns out, then truncated with a visible marker."""
    cleaned = scrub_pii(redact(text) if redact else text)
    if len(cleaned) > policy.max_chars:
        return cleaned[: policy.max_chars] + f"... [truncated {len(cleaned) - policy.max_chars} chars]"
    return cleaned
