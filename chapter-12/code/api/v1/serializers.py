from django.conf import settings
from rest_framework import serializers

from accounts.models import User
from chat.models import Conversation, Document, Message

class ErrorBodySerializer(serializers.Serializer):
    code = serializers.CharField()
    message = serializers.CharField()
    fields = serializers.DictField(child=serializers.ListField(), required=False)
    request_id = serializers.CharField(required=False)

class ErrorSerializer(serializers.Serializer):
    error = ErrorBodySerializer()

class UserSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)

    class Meta:
        model = User
        fields = ["id", "username", "email", "date_joined"]
        read_only_fields = fields

class ConversationSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)

    class Meta:
        model = Conversation
        fields = ["id", "title", "message_count", "created_at", "updated_at"]
        read_only_fields = ["message_count", "created_at", "updated_at"]

    def validate_title(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Title cannot be blank.")
        return value

class MessageSerializer(serializers.ModelSerializer):
    """What the client READS."""

    id = serializers.UUIDField(source="public_id", read_only=True)

    class Meta:
        model = Message
        fields = ["id", "role", "content", "model", "input_tokens",
                  "output_tokens", "created_at"]
        read_only_fields = fields

class MessageCreateSerializer(serializers.Serializer):
    """What the client SENDS: only the text. Role and tokens are ours to set."""

    content = serializers.CharField(max_length=20000, trim_whitespace=True)

class DocumentSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)

    class Meta:
        model = Document
        fields = ["id", "filename", "status", "created_at"]
        read_only_fields = ["status", "created_at"]

    def validate_filename(self, value):
        allowed = (".pdf", ".txt", ".docx", ".md")
        if not value.lower().endswith(allowed):
            raise serializers.ValidationError(
                f"Unsupported file type. Allowed: {', '.join(allowed)}."
            )
        return value

class UsageSerializer(serializers.Serializer):
    tokens_used_today = serializers.IntegerField()
    daily_limit = serializers.IntegerField()
    remaining = serializers.IntegerField()

class ClientConfigSerializer(serializers.Serializer):
    min_supported_version = serializers.CharField()
    latest_version = serializers.CharField()
    maintenance_mode = serializers.BooleanField()
