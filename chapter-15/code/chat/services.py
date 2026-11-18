"""Business logic lives here, not in views (Chapter 29 grows this layer)."""
import logging

from django.db import transaction
from django.db.models import F
from django.utils import timezone
from kombu.exceptions import OperationalError

from .models import Document, Message
from .tasks import ingest_document

logger = logging.getLogger(__name__)

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
    document.status = Document.Status.PROCESSING
    document.error = ""
    document.save(update_fields=["status", "error"])
    # Queue the job only AFTER the database transaction has committed.
    transaction.on_commit(lambda: _enqueue_ingestion(document.pk))

def _enqueue_ingestion(document_id):
    try:
        ingest_document.delay(document_id)       # ids, never model objects
    except OperationalError:                      # the broker is unreachable
        logger.exception("could not queue document %s", document_id)
        Document.objects.filter(pk=document_id).update(
            status=Document.Status.FAILED,
            error="Processing is temporarily unavailable. Please try again.",
        )
