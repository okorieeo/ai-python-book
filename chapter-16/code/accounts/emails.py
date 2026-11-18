from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core import signing
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from .exceptions import InvalidLink
from .models import User
from notifications.emailing import send_templated_email

VERIFY_SALT = "email-verification"


def send_verification_email(user):
    token = signing.dumps({"uid": user.pk, "email": user.email}, salt=VERIFY_SALT)
    link = f"{settings.FRONTEND_URL}/verify-email?token={token}"
    send_templated_email(
        "verify_email", user.email, {"name": user.name, "link": link},
        subject="Verify your email",
    )


def verify_email_token(token):
    """Return the user the token was issued for, or raise InvalidLink."""
    try:
        data = signing.loads(
            token, salt=VERIFY_SALT, max_age=settings.EMAIL_VERIFY_MAX_AGE
        )
        return User.objects.get(pk=data["uid"], email=data["email"])
    except (signing.BadSignature, User.DoesNotExist):
        raise InvalidLink()  # expired, tampered with, or email changed


def send_password_reset_email(user):
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    link = f"{settings.FRONTEND_URL}/reset-password?uid={uid}&token={token}"
    send_templated_email(
        "reset_password", user.email, {"name": user.name, "link": link},
        subject="Reset your password",
    )


def user_from_reset_link(uid, token):
    try:
        user = User.objects.get(pk=urlsafe_base64_decode(uid).decode())
    except (User.DoesNotExist, ValueError, UnicodeDecodeError):
        raise InvalidLink()
    if not user.is_active or not default_token_generator.check_token(
        user, token
    ):
        raise InvalidLink()
    return user
