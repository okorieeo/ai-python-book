"""Business logic lives here, not in views (Chapter 29 grows this layer)."""
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .models import Document, Message

@transaction.atomic
def add_message(conversation, role, content, **extra):
    message = Message.objects.create(
        conversation=conversation, role=role, content=content, **extra
    )
    type(conversation).objects.filter(pk=conversation.pk).update(
        message_count=F("message_count") + 1, updated_at=timezone.now()
    )
    return message

def start_ingestion(document):
    """Chapter 15 replaces this with a Celery task."""
    document.status = Document.Status.PROCESSING
    document.save(update_fields=["status"])
