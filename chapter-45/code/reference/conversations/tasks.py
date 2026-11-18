import logging

from celery import shared_task

from core.chat.history import Message as HistoryMessage

from .models import Conversation, Message

logger = logging.getLogger(__name__)


@shared_task(autoretry_for=(ConnectionError, TimeoutError), retry_backoff=True, max_retries=3)
def generate_title(conversation_public_id: str) -> None:
    """Idempotent: running it twice leaves the same title. Queue it with transaction.on_commit (Chapter 15)."""
    conversation = Conversation.objects.filter(public_id=conversation_public_id).first()
    if conversation is None or conversation.title:
        return                                                   # nothing to do, or already titled: safe to repeat
    first = Message.objects.filter(conversation=conversation, role="user").order_by("created_at").first()
    if first is None:
        return
    title = " ".join(first.content.split())[:60]
    Conversation.objects.filter(pk=conversation.pk, title="").update(title=title)      # only if still empty: no overwrite race
    logger.info("title generated", extra={"event": "title_generated", "fields": {"conversation": conversation_public_id}})
