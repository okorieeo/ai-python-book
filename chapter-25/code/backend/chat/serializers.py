from rest_framework import serializers

from .models import Message

MAX_MESSAGE_LENGTH = 8_000  # keep in step with the limit you chose in Chapter 17, section 17.7


class MessageCreateSerializer(serializers.Serializer):
    content = serializers.CharField(max_length=MAX_MESSAGE_LENGTH, trim_whitespace=True)
    client_id = serializers.UUIDField(required=False)


class MessageSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)

    class Meta:
        model = Message
        fields = ["id", "role", "content", "created_at", "client_id"]
