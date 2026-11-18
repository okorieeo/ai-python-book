from rest_framework import serializers

from core.responsible.consent_logic import Purpose, OPTIONAL


class ConsentChoiceSerializer(serializers.Serializer):
    purpose = serializers.ChoiceField(choices=sorted(p.value for p in OPTIONAL))
    granted = serializers.BooleanField()


class AcceptDocumentsSerializer(serializers.Serializer):
    terms_version = serializers.CharField(max_length=20)
    privacy_version = serializers.CharField(max_length=20)


class ConfirmPasswordSerializer(serializers.Serializer):
    password = serializers.CharField(write_only=True, trim_whitespace=False)


class DeleteAccountSerializer(ConfirmPasswordSerializer):
    confirm = serializers.CharField()

    def validate_confirm(self, value):
        if value != "DELETE":
            raise serializers.ValidationError('Type DELETE to confirm.')
        return value
