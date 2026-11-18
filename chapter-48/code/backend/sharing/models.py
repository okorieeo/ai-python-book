import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from chat.models import Conversation

from .tokens import link_state


class SharedLink(models.Model):
    """A read-only, snapshot link to one conversation. The token itself is never stored."""

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="shared_links")  # AC-12
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="shared_links")
    token_hash = models.CharField(max_length=64, unique=True, editable=False)   # SHA-256 hex digest
    created_at = models.DateTimeField(default=timezone.now, editable=False)     # also the snapshot time (AC-4)
    expires_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    view_count = models.PositiveIntegerField(default=0)                          # AC-13

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["conversation", "-created_at"], name="sharedlink_conv_idx")]

    def __str__(self) -> str:
        return f"SharedLink {self.public_id} ({self.state})"

    @property
    def state(self) -> str:
        return link_state(expires_at=self.expires_at, revoked_at=self.revoked_at)
