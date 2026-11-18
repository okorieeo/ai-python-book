from django.core.serializers.json import DjangoJSONEncoder
from django.db import models


class AuditEvent(models.Model):
    """One row per security-relevant fact: who did what, to what, when, from where.

    Append-only by design: the application creates events and never edits or deletes
    them. actor_id stores the user's public_id WITHOUT a foreign key, so the trail
    survives even if the account is deleted later.
    """

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    actor_id = models.UUIDField(null=True, blank=True)    # User.public_id; null if none
    action = models.CharField(max_length=64)              # "chat.conversation_deleted"
    target_type = models.CharField(max_length=64, blank=True)    # "conversation"
    target_id = models.CharField(max_length=64, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=300, blank=True)
    request_id = models.CharField(max_length=64, blank=True)     # links to the logs
    metadata = models.JSONField(default=dict, blank=True, encoder=DjangoJSONEncoder)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(
                fields=["actor_id", "-created_at"], name="audit_actor_created_idx"
            ),
            models.Index(
                fields=["action", "-created_at"], name="audit_action_created_idx"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.created_at:%Y-%m-%d %H:%M:%S} {self.action}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise PermissionError("Audit events are append-only and cannot be changed.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError("Audit events cannot be deleted by the application.")
