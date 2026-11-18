"""
Thumbs up / thumbs down on an assistant message, with a reason, and an optional short comment.
Pure rules plus a storage port; the Django model and view are in models.py and views.py.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from obs.scrub import scrub_pii

REASONS = ("wrong", "unhelpful", "harmful", "too_long", "too_short", "other")
RATABLE_STATUSES = {"complete", "truncated", "refused", "interrupted"}
MAX_COMMENT = 500


class FeedbackError(ValueError):
    """Bad input: becomes an HTTP 400."""


class MessageNotFound(Exception):
    """Missing, not an assistant message, or not in one of YOUR conversations: all look the same (HTTP 404)."""


@dataclass(frozen=True)
class MessageRef:
    message_id: int
    conversation_id: int
    owner_id: int
    role: str
    status: str


@dataclass(frozen=True)
class FeedbackRecord:
    user_id: int
    message_id: int
    conversation_id: int
    rating: int                      # +1 or -1
    reason: str
    comment: str
    may_use_for_improvement: bool


class FeedbackStore(Protocol):
    def get_message(self, message_id: int) -> MessageRef | None: ...
    def upsert(self, record: FeedbackRecord) -> bool: ...        # True if newly created, False if it replaced one


def submit_feedback(store: FeedbackStore, *, user_id: int, message_id: int, rating: object, reason: object = "",
                    comment: object = "", may_use_for_improvement: bool = False) -> FeedbackRecord:
    if rating not in (1, -1) or isinstance(rating, bool):
        raise FeedbackError("rating must be 1 or -1")
    reason_text = "" if reason is None else str(reason)
    if rating == -1:
        if reason_text not in REASONS:
            raise FeedbackError(f"a thumbs-down needs a reason: one of {', '.join(REASONS)}")
    else:
        reason_text = ""
    if not isinstance(comment, str):
        raise FeedbackError("comment must be text")
    clean_comment = scrub_pii(comment.strip())[:MAX_COMMENT]

    ref = store.get_message(message_id)
    # Ownership comes first, and a missing message and someone else's message are indistinguishable.
    if ref is None or ref.owner_id != user_id or ref.role != "assistant" or ref.status not in RATABLE_STATUSES:
        raise MessageNotFound()
    record = FeedbackRecord(user_id, ref.message_id, ref.conversation_id, int(rating), reason_text, clean_comment,
                            bool(may_use_for_improvement))
    store.upsert(record)
    return record
