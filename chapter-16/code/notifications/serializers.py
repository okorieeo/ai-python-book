from rest_framework import serializers

from .models import WebhookEndpoint
from .outbound import validate_webhook_url

KNOWN_EVENTS = {"*", "document.ready", "document.failed", "message.created"}


class EndpointSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)

    class Meta:
        model = WebhookEndpoint
        fields = ["id", "url", "events", "is_active", "created_at"]
        read_only_fields = [
            "is_active",
            "created_at",
        ]  # the secret is NOT here

    def validate_url(self, value):
        validate_webhook_url(value)
        return value

    def validate_events(self, value):
        unknown = set(value) - KNOWN_EVENTS
        if not value or unknown:
            raise serializers.ValidationError(
                f"Choose from: {', '.join(sorted(KNOWN_EVENTS))}."
            )
        return value
