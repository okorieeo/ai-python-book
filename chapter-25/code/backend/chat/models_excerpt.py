# Stand-in for your Chapter 7/11 models. Only Message.client_id and the UniqueConstraint are new in Chapter 25.
import uuid

from django.conf import settings
from django.db import models


class Conversation(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="conversations")
    title = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class Message(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=20)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    # NEW in Chapter 25: the key the phone generates once per message and repeats on every retry.
    client_id = models.UUIDField(null=True, blank=True, editable=False)

    class Meta:
        ordering = ["created_at", "id"]
        constraints = [
            # One message per (conversation, client_id). Rows with client_id NULL (the web client) never clash:
            # SQL treats NULLs as different values in a unique constraint.
            models.UniqueConstraint(fields=["conversation", "client_id"], name="uniq_message_client_id_per_conversation"),
        ]
