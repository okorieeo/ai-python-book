"""Idempotent handling of provider messages. Chapter 36 adds signature verification on top."""

from __future__ import annotations

from typing import Callable

from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import WebhookEvent


def record_webhook(
    provider: str, event_id: str, event_type: str, payload: dict
) -> tuple[WebhookEvent, bool]:
    """Store the message before doing anything else. A repeat of the same message is not stored twice."""
    try:
        with transaction.atomic():
            return (
                WebhookEvent.objects.create(
                    provider=provider,
                    event_id=event_id,
                    event_type=event_type,
                    payload=payload,
                ),
                True,
            )
    except IntegrityError:
        return WebhookEvent.objects.get(provider=provider, event_id=event_id), False


def process_once(event: WebhookEvent, handler: Callable[[WebhookEvent], None]) -> bool:
    """Run `handler` for this event at most once successfully. Returns True if it ran now.

    The handler and the status change commit together: if the handler raises, nothing it did
    is kept, the event is marked failed, and a later retry may try again.
    """
    with transaction.atomic():
        locked = WebhookEvent.objects.select_for_update().get(pk=event.pk)
        if locked.status == WebhookEvent.Status.PROCESSED:
            return False
        try:
            with transaction.atomic():
                handler(locked)
        except Exception as exc:
            locked.status = WebhookEvent.Status.FAILED
            locked.error = f"{type(exc).__name__}: {exc}"[:300]
            locked.save(update_fields=["status", "error"])
            return False
        locked.status = WebhookEvent.Status.PROCESSED
        locked.processed_at = timezone.now()
        locked.error = ""
        locked.save(update_fields=["status", "processed_at", "error"])
        return True
