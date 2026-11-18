"""Turn a disliked answer into a DRAFT eval case, but only with the person's permission."""
from __future__ import annotations

import json
from typing import Sequence

from obs.scrub import scrub_pii

from .service import FeedbackRecord

CONTEXT_TURNS = 6


def candidate_case(messages: Sequence[tuple[str, str]], answer_index: int, feedback: FeedbackRecord) -> str | None:
    """
    messages: the conversation as (role, text) pairs. answer_index: which message was rated.
    Returns one JSONL line for a human to finish (they must add checks or a rubric), or None if the person did
    not agree to their conversation being used to improve the product.
    """
    if not feedback.may_use_for_improvement or feedback.rating != -1:
        return None
    if not 0 < answer_index < len(messages) or messages[answer_index][0] != "assistant" or messages[answer_index - 1][0] != "user":
        raise ValueError("answer_index must point at an assistant message that follows a user message")
    start = max(0, answer_index - 1 - CONTEXT_TURNS)
    history = [[role, scrub_pii(text)] for role, text in messages[start:answer_index - 1]]
    while history and history[0][0] != "user":
        history.pop(0)
    obj = {
        "id": f"fb-{feedback.message_id}",
        "input": scrub_pii(messages[answer_index - 1][1]),
        "history": history,
        "tags": ["from-feedback", f"reason-{feedback.reason}"],
        "needs_review": True,
        "notes": scrub_pii(feedback.comment),
        "bad_answer": scrub_pii(messages[answer_index][1])[:1000],
    }
    return json.dumps(obj, ensure_ascii=False, sort_keys=True)
