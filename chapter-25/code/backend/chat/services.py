"""ADD to your chat/services.py (Chapter 11, extended in Chapter 17). New in Chapter 25: idempotent sends."""
import uuid

from django.db import IntegrityError, transaction

from .models import Conversation, Message


class ClientIdReused(Exception):
    """The same client_id arrived with different content: a client bug or tampering, never a retry."""


def _find_by_client_id(conversation: Conversation, client_id: uuid.UUID) -> Message | None:
    return Message.objects.filter(conversation=conversation, client_id=client_id).first()


def create_user_message(
    *, user, conversation: Conversation, content: str, client_id: uuid.UUID | None = None
) -> tuple[Message, bool]:
    """Create the user's message once, however many times the phone sends it.

    Returns (message, created). created is False when this client_id was already stored,
    which is how a retry after a lost response looks. Safe under concurrent duplicates.
    """
    if conversation.user_id != user.id:
        raise Conversation.DoesNotExist  # services never trust the caller to have checked ownership

    if client_id is None:  # web client or an old app version: no retry protection, same as before
        return Message.objects.create(conversation=conversation, role="user", content=content), True

    existing = _find_by_client_id(conversation, client_id)
    if existing is None:
        try:
            with transaction.atomic():  # a savepoint, so an IntegrityError does not poison an outer transaction
                message = Message.objects.create(
                    conversation=conversation, role="user", content=content, client_id=client_id
                )
            return message, True
        except IntegrityError:
            # Two copies of the same send raced and the other one won. The database decided; read its answer.
            existing = _find_by_client_id(conversation, client_id)
            if existing is None:
                raise  # a different integrity problem: do not hide it

    if existing.content != content:
        raise ClientIdReused
    return existing, False
