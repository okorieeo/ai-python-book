import asyncio
import logging

from celery import shared_task
from django.conf import settings

from ai.memory import USABLE, needs_summary
from ai.prompts import SUMMARY_SYSTEM_PROMPT
from ai.providers import ProviderError, get_provider

from .models import Conversation

logger = logging.getLogger(__name__)


def _transcript(messages) -> str:
    return "\n".join(f"{m.role.upper()}: {m.content[:2000]}" for m in messages)


@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def summarize_conversation(self, conversation_id: int) -> str:
    """Fold the oldest unsummarised messages into the conversation summary (idempotent and race-safe)."""
    conversation = Conversation.objects.get(pk=conversation_id)
    if not needs_summary(conversation):
        return "skipped"
    pending = list(conversation.messages.filter(id__gt=conversation.summary_through, status__in=USABLE)
                   .order_by("id"))
    fold = pending[: -settings.CHAT_SUMMARY_KEEP_RECENT]
    prompt = (f"Previous summary:\n{conversation.summary or '(none)'}\n\n"
              f"New messages:\n{_transcript(fold)}")
    try:
        new_summary = asyncio.run(get_provider().complete(
            system=SUMMARY_SYSTEM_PROMPT, messages=[{"role": "user", "content": prompt}], max_tokens=400))
    except ProviderError as exc:
        logger.warning("summary failed for conversation %s: %s", conversation_id, exc)
        raise self.retry(exc=exc)
    # Compare-and-set: if another worker already advanced the summary, our result is discarded.
    updated = Conversation.objects.filter(pk=conversation.pk, summary_through=conversation.summary_through
                                          ).update(summary=new_summary.strip()[:4000], summary_through=fold[-1].id)
    return "summarized" if updated else "lost_race"
