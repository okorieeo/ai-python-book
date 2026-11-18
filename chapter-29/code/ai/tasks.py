import asyncio

from celery import shared_task
from django.conf import settings

from chat.models import Conversation

from .dto import ChatMessage
from .factory import get_client
from .summarizer import summarize


@shared_task(bind=True, max_retries=2, default_retry_delay=60)
def refresh_summary(self, conversation_id: int):
    """Fold everything except the newest 10 messages into Conversation.summary, using the cheap model."""
    conv = Conversation.objects.get(pk=conversation_id)
    rows = list(conv.messages.filter(status__in=("complete", "truncated")).order_by("created_at", "id")
                .values_list("role", "content"))
    old = [ChatMessage(r, c) for r, c in rows[:-10]]
    if not old:
        return
    text = asyncio.run(summarize(client=get_client(), model=settings.AI_SUMMARY_MODEL,
                                 previous_summary=conv.summary or None, old_messages=old))
    if text:
        Conversation.objects.filter(pk=conversation_id).update(summary=text)
