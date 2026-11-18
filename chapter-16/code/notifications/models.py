import uuid

from django.conf import settings
from django.db import models


class EmailSuppression(models.Model):
    """Addresses we must not email again: they bounced or complained."""

    email = models.EmailField(unique=True)
    reason = models.CharField(max_length=20)  # "bounce" or "complaint"
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "email_suppressions"


class WebhookEvent(models.Model):
    """Every webhook we RECEIVE, stored once. Matches Chapter 7's table."""

    provider = models.CharField(max_length=30)
    event_id = models.CharField(max_length=100)
    event_type = models.CharField(max_length=60)
    payload = models.JSONField()
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "webhook_events"
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "event_id"], name="webhook_events_once"
            )
        ]


class WebhookEndpoint(models.Model):
    """A URL a customer gave us; we SEND signed events to it."""

    public_id = models.UUIDField(
        default=uuid.uuid4, unique=True, editable=False
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="endpoints",
    )
    url = models.URLField(max_length=500)
    secret = models.CharField(max_length=80)  # needed to sign: not a hash
    events = models.JSONField(
        default=list
    )  # ["document.ready", ...] or ["*"]
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "webhook_endpoints"


class WebhookDelivery(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending"
        SUCCEEDED = "succeeded"
        FAILED = "failed"

    endpoint = models.ForeignKey(
        WebhookEndpoint, on_delete=models.CASCADE, related_name="deliveries"
    )
    event_id = models.UUIDField(default=uuid.uuid4)
    event_type = models.CharField(max_length=60)
    payload = models.JSONField()
    status = models.CharField(
        max_length=10, choices=Status, default=Status.PENDING
    )
    attempts = models.PositiveSmallIntegerField(default=0)
    next_attempt_at = models.DateTimeField(auto_now_add=True)
    last_status_code = models.PositiveSmallIntegerField(null=True, blank=True)
    last_error = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "webhook_deliveries"
        indexes = [
            models.Index(
                fields=["status", "next_attempt_at"],
                name="idx_deliveries_due",
            )
        ]
