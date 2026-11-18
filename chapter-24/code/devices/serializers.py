import re

from rest_framework import serializers

from .models import PushDevice

# ExponentPushToken[xxxx] is the older spelling, ExpoPushToken[xxxx] the newer one.
TOKEN_PATTERN = re.compile(r"^(Expo|Exponent)PushToken\[[A-Za-z0-9_-]+\]$")

class DeviceSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)

    class Meta:
        model = PushDevice
        fields = ["id", "token", "platform", "device_name", "created_at"]
        # The token is accepted but never echoed back: it is a delivery address.
        # validators=[] removes the automatic "must be unique" check: registering the
        # same token twice is allowed, and is an update, not an error.
        extra_kwargs = {"token": {"write_only": True, "validators": []}}

    def validate_token(self, value):
        if not TOKEN_PATTERN.match(value):
            raise serializers.ValidationError("This is not an Expo push token.")
        return value
