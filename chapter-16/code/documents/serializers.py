from rest_framework import serializers

from .models import Document


class DocumentSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)

    class Meta:
        model = Document
        fields = [
            "id",
            "filename",
            "content_type",
            "size_bytes",
            "status",
            "error",
            "created_at",
        ]  # storage_key and sha256 stay private: clients never need them


class UploadUrlSerializer(serializers.Serializer):
    filename = serializers.CharField(max_length=200)
    content_type = serializers.ChoiceField(
        ["application/pdf", "image/png", "image/jpeg", "text/plain"]
    )
    size_bytes = serializers.IntegerField(min_value=1)
