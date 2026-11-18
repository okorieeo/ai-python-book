import uuid

from django.conf import settings
from django.db import models


def original_path(instance: "Attachment", filename: str) -> str:
    # The client's file name is NEVER part of the path: a random name cannot traverse folders or collide.
    return f"attachments/{instance.user_id}/original/{uuid.uuid4().hex}"


def processed_path(instance: "Attachment", filename: str) -> str:
    return f"attachments/{instance.user_id}/processed/{uuid.uuid4().hex}"


class Attachment(models.Model):
    class Kind(models.TextChoices):
        IMAGE = "image"
        DOCUMENT = "document"
        AUDIO = "audio"

    class Status(models.TextChoices):
        UPLOADED = "uploaded"      # saved, waiting for a worker
        PROCESSING = "processing"
        READY = "ready"            # safe to put in a model request
        REJECTED = "rejected"      # the FILE is not acceptable (permanent)
        FAILED = "failed"          # OUR side could not finish (providers down, too many retries)

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="attachments")
    message = models.ForeignKey("chat.Message", null=True, blank=True, on_delete=models.SET_NULL, related_name="attachments")

    kind = models.CharField(max_length=10, choices=Kind.choices)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.UPLOADED, db_index=True)
    error_code = models.CharField(max_length=40, blank=True)

    display_name = models.CharField(max_length=100, blank=True)  # for the UI only
    mime = models.CharField(max_length=60)                       # from the bytes, not from the client
    size_bytes = models.PositiveBigIntegerField(default=0)        # of the stored original, for quotas

    original = models.FileField(upload_to=original_path, blank=True, null=True)
    processed = models.FileField(upload_to=processed_path, blank=True, null=True)
    processed_mime = models.CharField(max_length=60, blank=True)
    sha256 = models.CharField(max_length=64, blank=True)

    width = models.PositiveIntegerField(null=True, blank=True)
    height = models.PositiveIntegerField(null=True, blank=True)
    page_count = models.PositiveIntegerField(null=True, blank=True)
    duration_seconds = models.FloatField(null=True, blank=True)
    visual_tokens = models.PositiveIntegerField(null=True, blank=True)
    transcript = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [models.Index(fields=["user", "created_at"])]
