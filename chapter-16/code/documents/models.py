import uuid

from django.conf import settings
from django.db import models


class Document(models.Model):
    class Status(models.TextChoices):
        UPLOADED = "uploaded"
        PROCESSING = "processing"
        READY = "ready"
        FAILED = "failed"

    public_id = models.UUIDField(
        default=uuid.uuid4, unique=True, editable=False
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="documents",
    )
    filename = models.CharField(max_length=200)  # what the user called it
    storage_key = models.CharField(max_length=300)  # where WE put it
    content_type = models.CharField(max_length=100)
    size_bytes = models.BigIntegerField()
    sha256 = models.CharField(max_length=64)
    status = models.CharField(
        max_length=12, choices=Status, default=Status.UPLOADED
    )
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "documents"
        indexes = [
            models.Index(
                fields=["user", "-created_at"], name="idx_documents_user"
            )
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    status__in=["uploaded", "processing", "ready", "failed"]
                ),
                name="documents_status_valid",
            ),
            models.UniqueConstraint(
                fields=["user", "sha256"], name="documents_user_sha256_key"
            ),
        ]
