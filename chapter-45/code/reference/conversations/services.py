"""The use cases. This file adapts the framework-free ChatService (core/chat/service.py) to the Django models."""
from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.module_loading import import_string

from core.chat.service import ChatService, StoredMessage

from .models import Conversation, Message


class DjangoChatRepo:
    """Implements the ChatRepo protocol with the ORM. Every lookup is scoped to the owner."""

    def get_conversation(self, user_id, public_id):
        obj = Conversation.objects.filter(user_id=user_id, public_id=public_id, archived_at__isnull=True).first()
        return str(obj.pk) if obj else None

    def _to_stored(self, m: Message) -> StoredMessage:
        return StoredMessage(m.pk, str(m.conversation_id), m.role, m.content, m.status, m.idempotency_key)

    def find_by_key(self, conversation_id, key):
        m = Message.objects.filter(conversation_id=conversation_id, idempotency_key=key).first()
        return self._to_stored(m) if m else None

    def add(self, conversation_id, role, content, *, status="ok", key=None):
        try:
            with transaction.atomic():
                m = Message.objects.create(conversation_id=conversation_id, role=role, content=content, status=status, idempotency_key=key)
        except IntegrityError:                       # two requests raced on the same key: the database picked a winner
            m = Message.objects.get(conversation_id=conversation_id, idempotency_key=key)
        Conversation.objects.filter(pk=conversation_id).update(updated_at=timezone.now())      # bump the list order
        return self._to_stored(m)

    def history(self, conversation_id):
        return [self._to_stored(m) for m in Message.objects.filter(conversation_id=conversation_id).order_by("created_at", "id")]

    def reply_to(self, user_message_id):
        user_msg = Message.objects.get(pk=user_message_id)
        reply = (Message.objects.filter(conversation_id=user_msg.conversation_id, role="assistant", created_at__gte=user_msg.created_at)
                 .order_by("created_at", "id").first())
        return self._to_stored(reply) if reply else None

    def set_status(self, message_id, status):
        Message.objects.filter(pk=message_id).update(status=status)


def build_chat_service(provider=None) -> ChatService:
    """settings.CHAT_PROVIDER is a dotted path to a class with .complete(messages, timeout=...) (Chapter 29)."""
    provider = provider or import_string(settings.CHAT_PROVIDER)()
    return ChatService(repo=DjangoChatRepo(), provider=provider)       # Chapter 34's check_input and prepare plug in here


@transaction.atomic
def create_conversation(*, user, title: str = "") -> Conversation:
    return Conversation.objects.create(user=user, title=title[:200])


@transaction.atomic
def archive_conversation(*, user, conversation: Conversation) -> None:
    Conversation.objects.filter(pk=conversation.pk, user=user).update(archived_at=timezone.now())
