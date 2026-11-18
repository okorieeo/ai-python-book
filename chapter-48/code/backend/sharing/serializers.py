from rest_framework import serializers

from .tokens import EXPIRY_CHOICES


class ShareLinkCreateSerializer(serializers.Serializer):
    expires_in = serializers.ChoiceField(choices=sorted(EXPIRY_CHOICES), default="7d")


class ShareLinkSerializer(serializers.Serializer):
    """What the owner sees when listing. No url, ever (AC-2)."""

    id = serializers.UUIDField(source="public_id", read_only=True)
    state = serializers.ChoiceField(choices=["active", "expired", "revoked"], read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    expires_at = serializers.DateTimeField(read_only=True, allow_null=True)
    view_count = serializers.IntegerField(read_only=True)


class ShareLinkCreatedSerializer(ShareLinkSerializer):
    url = serializers.URLField(read_only=True)


class SharedMessageSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=["user", "assistant"])
    content = serializers.CharField()
    created_at = serializers.DateTimeField()


class SharedConversationSerializer(serializers.Serializer):
    """The public shape: no owner name, email or id (see the spec, Security and privacy)."""

    title = serializers.CharField()
    shared_at = serializers.DateTimeField()
    messages = SharedMessageSerializer(many=True)
