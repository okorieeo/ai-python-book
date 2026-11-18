"""A small, fail-closed safety pipeline around the model call."""
from __future__ import annotations

import enum
import re
from dataclasses import dataclass, field
from typing import Mapping, Protocol

from core.security.redaction import redact


class Action(enum.StrEnum):
    ALLOW = "allow"
    BLOCK = "block"
    SUPPORT = "support"   # show a caring, reviewed message with local resources instead of calling the model
    REDACT = "redact"     # allow, but with this replacement text


@dataclass(frozen=True)
class Verdict:
    action: Action
    category: str = ""
    reason: str = ""
    text: str = ""        # what to show or send instead, when the action needs one


class Classifier(Protocol):
    def classify(self, text: str) -> Mapping[str, float]:
        """Return a score from 0 to 1 per category, e.g. {"violence": 0.02, "hate": 0.9}."""


_CRISIS = re.compile(
    r"(?i)\b(kill(ing)?\s+myself|end(ing)?\s+my\s+life|want\s+to\s+die|suicid\w*|"
    r"hurt(ing)?\s+myself|self[- ]harm|no\s+reason\s+to\s+live)\b"
)


def looks_like_crisis(text: str) -> bool:
    """High-recall phrase check. It will over-trigger on purpose; a gentle message costs little."""
    return bool(_CRISIS.search(text))


@dataclass
class SafetyConfig:
    thresholds: Mapping[str, float] = field(default_factory=lambda: {
        "violence": 0.8, "hate": 0.8, "illegal": 0.8, "sexual_minors": 0.1, "self_harm": 0.5, "jailbreak": 0.9})
    fail_closed: bool = True
    support_message: str = "SUPPORT_MESSAGE_FROM_SETTINGS"   # reviewed text with local resources (settings)
    block_message: str = "I can't help with that request."
    canary: str = ""      # a random string placed in the system prompt to detect leaks


class SafetyPipeline:
    def __init__(self, classifier: Classifier, config: SafetyConfig | None = None):
        self.classifier = classifier
        self.config = config or SafetyConfig()

    def _scores(self, text: str) -> Mapping[str, float] | None:
        try:
            return self.classifier.classify(text)
        except Exception:  # noqa: BLE001 - any failure is handled by the fail-closed rule
            return None

    def check_input(self, text: str) -> Verdict:
        if looks_like_crisis(text):
            return Verdict(Action.SUPPORT, "self_harm", "crisis_phrase", self.config.support_message)
        scores = self._scores(text)
        if scores is None:
            if self.config.fail_closed:
                return Verdict(Action.BLOCK, "unavailable", "classifier_unavailable", self.config.block_message)
            return Verdict(Action.ALLOW, reason="classifier_unavailable_fail_open")
        for category, limit in self.config.thresholds.items():
            if scores.get(category, 0.0) >= limit:
                if category == "self_harm":
                    return Verdict(Action.SUPPORT, category, "classifier", self.config.support_message)
                return Verdict(Action.BLOCK, category, "classifier", self.config.block_message)
        return Verdict(Action.ALLOW)

    def check_output(self, text: str) -> Verdict:
        if self.config.canary and self.config.canary in text:
            return Verdict(Action.BLOCK, "system_prompt_leak", "canary_found", self.config.block_message)
        scores = self._scores(text)
        if scores is None and self.config.fail_closed:
            return Verdict(Action.BLOCK, "unavailable", "classifier_unavailable", self.config.block_message)
        for category, limit in self.config.thresholds.items():
            if category != "jailbreak" and (scores or {}).get(category, 0.0) >= limit:
                return Verdict(Action.BLOCK, category, "classifier", self.config.block_message)
        cleaned = redact(text)
        if cleaned != text:
            return Verdict(Action.REDACT, "secret_in_output", "secret_pattern", cleaned)
        return Verdict(Action.ALLOW)
