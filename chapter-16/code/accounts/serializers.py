from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.files.storage import storages
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed

from .models import Farm, User


class UserSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    avatar_url = serializers.SerializerMethodField()

    def get_avatar_url(self, user):
        if not user.avatar_key:
            return None
        return storages["default"].url(user.avatar_key)

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "name",
            "role",
            "email_verified",
            "avatar_url",
            "created_at",
        ]
        read_only_fields = ["email", "role", "email_verified", "created_at"]


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    name = serializers.CharField(max_length=200)
    password = serializers.CharField(write_only=True)

    def validate_email(self, value):
        value = value.lower()
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError(
                "An account with this email exists."
            )
        return value

    def validate(self, attrs):
        candidate = User(email=attrs["email"], name=attrs["name"])
        try:  # length, common passwords, too similar to the email or name
            validate_password(attrs["password"], candidate)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(
                {"password": list(exc.messages)}
            )
        return attrs

    def create(self, data):
        return User.objects.create_user(**data)


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField()

    def validate(self, attrs):
        user = authenticate(
            email=attrs["email"].lower(), password=attrs["password"]
        )
        if (
            user is None
        ):  # same answer for "no such email" and "wrong password"
            raise AuthenticationFailed("Incorrect email or password.")
        attrs["user"] = user
        return attrs


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True)


class FarmSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)

    class Meta:
        model = Farm
        fields = ["id", "name", "created_at"]
        read_only_fields = ["created_at"]
