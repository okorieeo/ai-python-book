from rest_framework import serializers

from core.api_fields import LocalDateTimeField

from .models import Task


class TaskSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    due = LocalDateTimeField(source="due_at", required=False, allow_null=True)
    remind = LocalDateTimeField(source="remind_at", required=False, allow_null=True)

    class Meta:
        model = Task
        # An explicit allow-list (Chapter 17): the user, status timestamps and ids can
        # never be set by a client.
        fields = ["id", "title", "notes", "status", "priority", "due", "remind", "estimate_minutes", "completed_at", "created_at"]
        read_only_fields = ["completed_at", "created_at"]
