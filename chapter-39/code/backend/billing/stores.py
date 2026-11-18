from django.db import IntegrityError, transaction

from .models import ProcessedWebhookEvent


class DbIdempotencyStore:
    """claim() inserts a row; the database, not Python, decides who was first when two deliveries race."""

    def claim(self, key: str) -> bool:
        try:
            with transaction.atomic():
                ProcessedWebhookEvent.objects.create(key=key)
            return True
        except IntegrityError:
            return False

    def release(self, key: str) -> None:
        ProcessedWebhookEvent.objects.filter(key=key).delete()
