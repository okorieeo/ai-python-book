import uuid

from django.conf import settings
from django.db import models

class PushDevice(models.Model):
    """One phone (really: one app install) that may receive push notifications."""

    class Platform(models.TextChoices):
        IOS = "ios"
        ANDROID = "android"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="push_devices",
    )
    # UNIQUE across all users: a token belongs to one phone, and a phone has one
    # signed-in account at a time. If Bo signs in on Ada's old phone, the row moves.
    token = models.CharField(max_length=200, unique=True)
    platform = models.CharField(max_length=10, choices=Platform)
    device_name = models.CharField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "push_devices"
        indexes = [
            models.Index(fields=["user", "is_active"], name="idx_push_devices_user")
        ]
