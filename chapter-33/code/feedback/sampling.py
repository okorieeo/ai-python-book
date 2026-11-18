"""Which answers do humans review? Not all of them, and not at random only."""
from __future__ import annotations

from evals.rollout import in_rollout

NEGATIVE_STATUSES = {"failed", "interrupted", "refused", "truncated"}


def review_percent(*, status: str, rating: int | None, base_percent: float) -> float:
    """Every thumbs-down is reviewed; bad endings are reviewed half the time; the rest at the base rate."""
    if rating == -1:
        return 100.0
    if status in NEGATIVE_STATUSES:
        return max(50.0, base_percent)
    return base_percent


def needs_review(message_id: int, *, status: str, rating: int | None, base_percent: float = 2.0,
                 salt: str = "review") -> bool:
    return in_rollout(message_id, review_percent(status=status, rating=rating, base_percent=base_percent), salt)
