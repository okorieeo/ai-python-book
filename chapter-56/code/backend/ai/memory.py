"""Conversation memory: a summary of the distant past plus a token-budgeted window of recent messages.

    context sent to the model  =  system prompt + summary  +  messages after `summary_through` (trimmed to fit)

A background task (chat/tasks.py) folds older messages into the summary. Until it catches up, the window
simply trims the oldest unsummarised messages, so a slow task never breaks a chat.
"""
from dataclasses import dataclass

from django.conf import settings

from chat.models import Conversation, Message

from .prompts import SYSTEM_PROMPT

USABLE = (Message.Status.COMPLETE, Message.Status.STOPPED)


def estimate_tokens(text: str) -> int:
    """About four characters per token for English. Good enough for budgeting; the provider reports
    the exact numbers after each reply, and those are what we record."""
    return max(1, (len(text) + 3) // 4)


@dataclass(frozen=True)
class Context:
    system: str
    messages: list[dict]
    trimmed: int  # how many unsummarised messages did not fit in the budget


def build_system_prompt(conversation: Conversation) -> str:
    if conversation.summary:
        return f"{SYSTEM_PROMPT}\n\nSummary of the earlier conversation:\n{conversation.summary}"
    return SYSTEM_PROMPT


def build_context(conversation: Conversation, *, budget: int | None = None) -> Context:
    budget = budget or settings.CHAT_CONTEXT_TOKEN_BUDGET
    system = build_system_prompt(conversation)
    remaining = budget - estimate_tokens(system)

    rows = list(
        conversation.messages.filter(id__gt=conversation.summary_through, status__in=USABLE)
        .exclude(content="").order_by("-id").values("role", "content")[:200]
    )
    kept: list[dict] = []
    for row in rows:  # newest first: the latest messages matter most
        cost = estimate_tokens(row["content"])
        if kept and cost > remaining:
            break
        kept.append(row)
        remaining -= cost
    kept.reverse()
    while kept and kept[0]["role"] != "user":  # the API wants the conversation to start with the user
        kept.pop(0)
    return Context(system=system, messages=kept, trimmed=len(rows) - len(kept))


def unsummarised_tokens(conversation: Conversation) -> tuple[int, int]:
    """(message count, token estimate) of everything the summary does not cover yet."""
    contents = list(conversation.messages.filter(id__gt=conversation.summary_through, status__in=USABLE)
                    .values_list("content", flat=True))
    return len(contents), sum(estimate_tokens(c) for c in contents)


def needs_summary(conversation: Conversation) -> bool:
    count, tokens = unsummarised_tokens(conversation)
    trigger = int(settings.CHAT_CONTEXT_TOKEN_BUDGET * 0.6)
    return count > settings.CHAT_SUMMARY_KEEP_RECENT and tokens >= trigger
