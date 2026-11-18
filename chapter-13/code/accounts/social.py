from django.conf import settings
from django.db import transaction
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from rest_framework.exceptions import ValidationError

from .models import SocialAccount, User


def verify_google_token(token):
    """Check Google's signature, audience and expiry; return the claims."""
    try:
        return id_token.verify_oauth2_token(
            token, google_requests.Request(), settings.GOOGLE_CLIENT_ID
        )
    except ValueError:
        raise ValidationError({"id_token": ["Google rejected this token."]})


@transaction.atomic
def user_from_google(token):
    claims = verify_google_token(token)
    if not claims.get("email_verified"):
        raise ValidationError(
            {"id_token": ["Your Google email is not verified."]}
        )
    link = SocialAccount.objects.filter(
        provider="google", uid=claims["sub"]
    ).first()
    if link:
        return link.user
    email = claims["email"].lower()
    user = User.objects.filter(email=email).first()
    if user is None:  # first sign-in: create the account, no password needed
        user = User.objects.create_user(
            email,
            password=None,
            name=claims.get("name") or email,
            email_verified=True,
        )
    elif not user.email_verified:
        # Someone may have pre-registered this address with a password of
        # their own. Google has now verified the real owner: discard it.
        user.set_unusable_password()
        user.email_verified = True
        user.save(update_fields=["password", "email_verified", "updated_at"])
    SocialAccount.objects.create(
        user=user, provider="google", uid=claims["sub"]
    )
    return user
