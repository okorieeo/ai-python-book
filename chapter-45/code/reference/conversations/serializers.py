from rest_framework import serializers

from .models import Conversation, Message


class MessageSerializer(serializers.ModelSerializer):
    ai_generated = serializers.BooleanField(read_only=True)

    class Meta:
        model = Message
        fields = ["public_id", "role", "content", "status", "model_name", "ai_generated", "created_at"]
        read_only_fields = fields                    # nothing is writable through this serializer


class ConversationSerializer(serializers.ModelSerializer):
    last_message = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = ["public_id", "title", "created_at", "updated_at", "last_message"]
        read_only_fields = ["public_id", "created_at", "updated_at", "last_message"]

    def get_last_message(self, obj) -> str | None:
        last = getattr(obj, "last_messages", [])
        return last[0].content[:120] if last else None


class SendMessageSerializer(serializers.Serializer):
    content = serializers.CharField(max_length=8000, trim_whitespace=True)
