from rest_framework import serializers

from .models import Attachment


class AttachmentSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)

    class Meta:
        model = Attachment
        fields = ["id", "kind", "status", "error_code", "display_name", "mime", "width", "height",
                  "page_count", "duration_seconds", "created_at"]
        read_only_fields = fields
