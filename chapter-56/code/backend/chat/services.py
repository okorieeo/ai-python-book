"""Business rules for one chat turn. Synchronous and database-only, so the consumer can call it
through sync_to_async and tests can call it directly (Chapter 11's service layer)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from django.conf import settings
from django.db import transaction

from ai.memory import needs_summary

from . import usage
from .models import Conversation, Message


class ChatError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


@dataclass(frozen=True)
class Turn:
    conversation: Conversation
    user_message: Message
    assistant_message: Message
    created_conversation: bool


def start_turn(*, user, conversation_public_id, content, daily_limit: int) -> Turn:
    """Validate, enforce the quota, and save the user's message plus an empty assistant message.
    Raises ChatError with a code the client can act on."""
    if not isinstance(content, str) or not content.strip():
        raise ChatError("invalid_message", "Write a message first.")
    content = content.strip()
    if len(content) > settings.CHAT_MAX_MESSAGE_CHARS:
        raise ChatError("too_long", f"Messages can be at most {settings.CHAT_MAX_MESSAGE_CHARS} characters.")

    with transaction.atomic():
        created = conversation_public_id in (None, "")
        if created:
            conversation = Conversation.objects.create(user=user, title=content[:60])
        else:
            try:  # owner-scoped lookup: someone else's conversation simply does not exist (Chapter 17.3)
                conversation = Conversation.objects.get(user=user, public_id=uuid.UUID(str(conversation_public_id)))
            except (Conversation.DoesNotExist, ValueError):
                raise ChatError("not_found", "That conversation does not exist.") from None

        quota = usage.try_consume_message(user, daily_limit)
        if not quota.allowed:
            transaction.set_rollback(True)  # do not keep an empty conversation created for a refused message
            raise ChatError("limit_reached", f"You have used all {quota.limit} messages for today.")

        user_message = Message.objects.create(conversation=conversation, role=Message.Role.USER, content=content)
        assistant_message = Message.objects.create(conversation=conversation, role=Message.Role.ASSISTANT,
                                                   status=Message.Status.STREAMING)
    return Turn(conversation, user_message, assistant_message, created)


def finish_turn(turn: Turn, *, text: str, status: str, input_tokens: int = 0, output_tokens: int = 0) -> None:
    """Save the assistant's reply (complete or partial) and record what it cost."""
    with transaction.atomic():
        Message.objects.filter(pk=turn.assistant_message.pk).update(
            content=text, status=status, input_tokens=input_tokens, output_tokens=output_tokens)
        usage.add_tokens(turn.conversation.user, input_tokens, output_tokens)
        Conversation.objects.get(pk=turn.conversation.pk).save(update_fields=["updated_at"])  # bumps the sort order
    if status in (Message.Status.COMPLETE, Message.Status.STOPPED):
        maybe_schedule_summary(turn.conversation.pk)


def fail_turn(turn: Turn) -> None:
    """The model failed before saying anything: mark the message and give the user their message back."""
    with transaction.atomic():
        Message.objects.filter(pk=turn.assistant_message.pk).update(status=Message.Status.ERROR)
        usage.refund_message(turn.conversation.user)


def maybe_schedule_summary(conversation_id: int) -> None:
    from .tasks import summarize_conversation

    conversation = Conversation.objects.get(pk=conversation_id)
    if needs_summary(conversation):
        transaction.on_commit(lambda: summarize_conversation.delay(conversation_id))
