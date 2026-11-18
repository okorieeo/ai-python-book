"""Business rules for sharing. Views stay thin; everything that matters is here."""
from __future__ import annotations

from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from audit.services import Action, record
from chat.models import Conversation

from .models import SharedLink
from .tokens import expiry_from_choice, generate_token, hash_token, public_url


class LinkNotFound(Exception):
    """Unknown, expired and revoked links all raise this one error (AC-6)."""


def create_share_link(*, user, conversation: Conversation, expires_in: str | None, request=None):
    """Return (link, url). The url exists only in this return value (AC-2)."""
    if conversation.user_id != user.id:
        raise Conversation.DoesNotExist  # services never trust the caller to have checked ownership (AC-7)
    now = timezone.now()
    token = generate_token()
    with transaction.atomic():
        link = SharedLink.objects.create(
            conversation=conversation,
            created_by=user,
            token_hash=token.digest,
            created_at=now,
            expires_at=expiry_from_choice(expires_in, now=now),
        )
        record(Action.SHARE_LINK_CREATED, request=request, actor=user, target=link,
               metadata={"expires_at": link.expires_at.isoformat() if link.expires_at else "never"})  # AC-9
    return link, public_url(settings.SHARE_PUBLIC_BASE_URL, token.raw)


def list_share_links(*, user, conversation: Conversation):
    if conversation.user_id != user.id:
        raise Conversation.DoesNotExist
    return conversation.shared_links.all()


def revoke_share_link(*, user, link: SharedLink, request=None) -> None:
    """Idempotent: revoking twice is not an error and writes only one audit event."""
    if link.created_by_id != user.id:
        raise SharedLink.DoesNotExist
    if link.revoked_at is not None:
        return
    with transaction.atomic():
        link.revoked_at = timezone.now()
        link.save(update_fields=["revoked_at"])
        record(Action.SHARE_LINK_REVOKED, request=request, actor=user, target=link)  # AC-9


def resolve_public_link(raw_token: str) -> SharedLink:
    """Find an ACTIVE link from the token in the URL, or raise LinkNotFound (AC-6)."""
    try:
        link = SharedLink.objects.select_related("conversation").get(token_hash=hash_token(raw_token))
    except SharedLink.DoesNotExist:
        raise LinkNotFound from None
    if link.state != "active":
        raise LinkNotFound
    return link


def snapshot_messages(link: SharedLink):
    """Only messages that existed when the link was created (AC-4)."""
    return link.conversation.messages.filter(created_at__lte=link.created_at).order_by("created_at", "id")


def record_view(link: SharedLink) -> None:
    """Atomic increment: two simultaneous viewers must not lose a count (AC-13)."""
    SharedLink.objects.filter(pk=link.pk).update(view_count=F("view_count") + 1)
