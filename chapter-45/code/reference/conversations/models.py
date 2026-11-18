import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q


class Conversation(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="conversations")
    title = models.CharField(max_length=200, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        indexes = [models.Index(fields=["user", "-updated_at"], name="conv_user_updated_idx")]
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return f"Conversation {self.public_id}"


class Message(models.Model):
    class Role(models.TextChoices):
        USER = "user"
        ASSISTANT = "assistant"

    class Status(models.TextChoices):
        PENDING = "pending"
        OK = "ok"
        FAILED = "failed"
        BLOCKED = "blocked"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=12, choices=Role.choices)
    content = models.TextField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.OK)
    idempotency_key = models.CharField(max_length=80, null=True, blank=True)
    model_name = models.CharField(max_length=80, blank=True)           # which model wrote it (Chapter 34 labels AI output)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [models.Index(fields=["conversation", "created_at"], name="msg_conv_created_idx")]
        constraints = [
            models.UniqueConstraint(fields=["conversation", "idempotency_key"], name="uniq_msg_conv_key"),
            models.CheckConstraint(check=Q(role__in=["user", "assistant"]), name="msg_role_valid"),
        ]

    @property
    def ai_generated(self) -> bool:
        return self.role == self.Role.ASSISTANT
