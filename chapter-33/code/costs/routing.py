"""
Send easy work to the cheap model and hard work to the strong one. Rules, not magic: every rule here should be
justified by an eval run showing the cheap model is good enough for that kind of request.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RouteConfig:
    strong_model: str
    cheap_model: str
    cheap_tags: frozenset[str] = frozenset({"classification", "extraction", "title", "summary", "smalltalk"})
    always_strong_tags: frozenset[str] = frozenset({"safety", "legal", "medical"})
    max_cheap_input_tokens: int = 4000


@dataclass(frozen=True)
class RouteFeatures:
    tags: frozenset[str] = frozenset()
    estimated_input_tokens: int = 0
    has_attachment: bool = False
    retry_after_bad_answer: bool = False


@dataclass(frozen=True)
class Route:
    model: str
    reason: str


def route(features: RouteFeatures, cfg: RouteConfig) -> Route:
    """The order of the rules IS the policy: safety beats cost, and doubt means the strong model."""
    if features.tags & cfg.always_strong_tags:
        return Route(cfg.strong_model, "sensitive topic")
    if features.retry_after_bad_answer:
        return Route(cfg.strong_model, "person asked again after a bad answer")
    if features.has_attachment:
        return Route(cfg.strong_model, "attachment")
    if features.estimated_input_tokens > cfg.max_cheap_input_tokens:
        return Route(cfg.strong_model, "long input")
    if features.tags and features.tags <= cfg.cheap_tags:
        return Route(cfg.cheap_model, "simple task")
    return Route(cfg.strong_model, "default")
