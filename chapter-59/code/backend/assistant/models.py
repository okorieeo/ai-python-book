import uuid

from django.conf import settings
from django.db import models


class AssistantThread(models.Model):
    """One conversation. `messages` holds the raw history, including tool_use and
    tool_result blocks."""

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="assistant_threads")
    messages = models.JSONField(default=list)
    # tool_result blocks already finished in a paused turn
    paused_results = models.JSONField(default=list)
    archived = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["user", "archived", "-updated_at"], name="thread_user_active_idx")]


class PendingAction(models.Model):
    """A tool call that waits for the person's yes or no. Only these stored arguments
    can ever run."""

    class Status(models.TextChoices):
        PENDING = "pending"
        APPROVED = "approved"
        DECLINED = "declined"
        EXPIRED = "expired"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    thread = models.ForeignKey(AssistantThread, on_delete=models.CASCADE, related_name="pending_actions")
    tool_use_id = models.CharField(max_length=100)
    tool = models.CharField(max_length=64)
    arguments = models.JSONField()
    # written by our code, shown to the person
    summary = models.CharField(max_length=500)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.PENDING)
    expires_at = models.DateTimeField()
    decided_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["thread", "tool_use_id"], name="pending_unique_tool_use")]


class ToolCallLog(models.Model):
    """What the assistant did, without the arguments (they can hold personal text; see
    Chapter 17)."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    tool = models.CharField(max_length=64)
    ok = models.BooleanField()
    code = models.CharField(max_length=40, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class AssistantUsage(models.Model):
    """Token ledger: the source of truth for cost, as in Chapter 29."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    thread = models.ForeignKey(AssistantThread, null=True, on_delete=models.SET_NULL)
    model = models.CharField(max_length=64)
    input_tokens = models.PositiveIntegerField()
    output_tokens = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)


class SentNotification(models.Model):
    """The database refuses a second row with the same key, which is what makes
    reminders idempotent."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    kind = models.CharField(max_length=32)  # "event_reminder", "task_reminder"
    key = models.CharField(max_length=120)
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "kind", "key"], name="notification_once")]


class PushDevice(models.Model):
    """Expo push tokens. If Chapter 24 already created this, reuse that model and delete
    this one."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="push_devices")
    token = models.CharField(max_length=200, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
