"""Write audit events. Call record() inside the transaction of the change."""
import enum

from django.conf import settings

from core.security.redaction import redact_data

from .context import request_context
from .models import AuditEvent


class Action(enum.StrEnum):
    LOGIN_SUCCEEDED = "auth.login_succeeded"
    LOGIN_FAILED = "auth.login_failed"
    PASSWORD_CHANGED = "auth.password_changed"
    API_TOKEN_CREATED = "auth.api_token_created"
    ROLE_CHANGED = "access.role_changed"
    CONVERSATION_DELETED = "chat.conversation_deleted"
    DATA_EXPORTED = "privacy.data_exported"
    ACCOUNT_DELETED = "privacy.account_deleted"


def record(
    action, *, request=None, actor=None, target=None, metadata: dict | None = None
) -> AuditEvent:
    """Create one audit event.

    request:  the HTTP request, if any (adds IP address, user agent and request id)
    actor:    who did it (defaults to request.user)
    target:   the model instance the action was about
    metadata: a few small facts. Secrets are redacted, but do not put them here.
    """
    context = {}
    if request is not None:
        context = request_context(request, trusted_proxies=settings.TRUSTED_PROXY_COUNT)
        if actor is None:
            actor = getattr(request, "user", None)
    target_id = "" if target is None else str(getattr(target, "public_id", target.pk))
    return AuditEvent.objects.create(
        action=str(action),
        actor_id=getattr(actor, "public_id", None),  # AnonymousUser: None
        target_type="" if target is None else target._meta.model_name,
        target_id=target_id,
        metadata=redact_data(metadata or {}),
        **context,
    )
