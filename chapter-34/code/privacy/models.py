import uuid

from django.conf import settings
from django.db import models

from core.responsible.consent_logic import Purpose


class LegalDocument(models.Model):
    """One published version of the Terms or the Privacy Policy. Never edited: publish a new row."""

    class Kind(models.TextChoices):
        TERMS = "terms", "Terms of Service"
        PRIVACY = "privacy", "Privacy Policy"

    kind = models.CharField(max_length=20, choices=Kind.choices)
    version = models.CharField(max_length=20)          # e.g. "2026-11-05"
    effective_at = models.DateTimeField()
    sha256 = models.CharField(max_length=64)           # proves which exact text was shown
    url = models.URLField()
    summary_of_changes = models.TextField(blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["kind", "version"], name="uniq_legal_doc_version")]
        ordering = ["-effective_at"]


class ConsentEvent(models.Model):
    """Append-only: a withdrawal is a new row, never an edit."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="consent_events")
    purpose = models.CharField(max_length=30, choices=[(p.value, p.value) for p in Purpose])
    granted = models.BooleanField()
    document_version = models.CharField(max_length=20)
    request_id = models.CharField(max_length=64, blank=True)   # no IP address: we do not need it
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["user", "purpose", "-created_at"])]
        ordering = ["created_at", "id"]

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise PermissionError("Consent events are append-only; create a new event instead.")
        super().save(*args, **kwargs)


class DeletionRequest(models.Model):
    """Proof that an erasure was requested and finished. Holds the public id, never the email."""

    class Status(models.TextChoices):
        SCHEDULED = "scheduled"
        CANCELLED = "cancelled"
        RUNNING = "running"
        PARTIAL = "partial"       # some stores failed; the job retries
        COMPLETE = "complete"

    user_public_id = models.UUIDField(db_index=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.SCHEDULED)
    requested_at = models.DateTimeField(auto_now_add=True)
    scheduled_for = models.DateTimeField()
    completed_at = models.DateTimeField(null=True, blank=True)
    done_stores = models.JSONField(default=list)       # names of erasers that succeeded
    failed_stores = models.JSONField(default=list)
    request_id = models.CharField(max_length=64, blank=True)

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
