"""Where billing meets the AI layer (Chapters 27 to 30): pick the model, check, then record."""

from __future__ import annotations

from typing import Optional

from django.conf import settings

from .entitlements import has_feature
from .permissions import FeatureNotInPlan
from .usage import check_can_use, record_usage

MICRO = 1_000_000


def pick_model(user) -> str:
    """The plan decides which model a user gets. Model ids come from settings (Chapter 27)."""
    if has_feature(user, "ai.premium_models"):
        return settings.BILLING_MODEL_PREMIUM
    return settings.BILLING_MODEL_STANDARD


def check_before_model_call(user) -> None:
    """Call this BEFORE paying for a model call. Raises FeatureNotInPlan or LimitExceeded."""
    if not has_feature(user, "ai.chat"):
        raise FeatureNotInPlan(code="feature_not_in_plan")
    check_can_use(user, "ai.message", 1)


def record_ai_message(
    user,
    *,
    request_id: str,
    model_id: str,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
    conversation_id: Optional[int] = None,
    weight: int = 1,
):
    """Call this AFTER the model answered, with the numbers from Chapter 27's TokenUsage and cost_usd.

    It never refuses: the money is already spent. Ids and counts only, never message text.
    `weight` lets a heavier request count as more than one message: an agent run that made six
    model calls (Chapter 30) can pass weight=6 so the plan limit follows real cost.
    """
    return record_usage(
        user,
        "ai.message",
        weight,
        f"ai-message:{request_id}",
        cost_micro_usd=round(cost_usd * MICRO),
        meta={
            "model": model_id,
            "in": input_tokens,
            "out": output_tokens,
            "conversation": conversation_id,
        },
    )
