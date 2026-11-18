"""Short-lived, single-use tickets so mobile apps and the Next.js app can authenticate a WebSocket."""
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from channels.security.websocket import OriginValidator
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core import signing
from django.core.cache import cache

TICKET_SALT = "websocket-ticket"
TICKET_MAX_AGE_SECONDS = 30

def make_ticket(user) -> str:
    """A signed, expiring token that says 'this is user N'. Issued by the REST API to a logged-in user."""
    return signing.dumps({"uid": user.pk}, salt=TICKET_SALT)

def read_ticket(ticket: str) -> int | None:
    try:
        return signing.loads(ticket, salt=TICKET_SALT, max_age=TICKET_MAX_AGE_SECONDS)["uid"]
    except (signing.BadSignature, KeyError):       # BadSignature also covers SignatureExpired
        return None

@database_sync_to_async
def _get_user(user_id: int):
    try:
        user = get_user_model().objects.get(pk=user_id, is_active=True)
    except get_user_model().DoesNotExist:
        return AnonymousUser()
    return user

class TicketAuthMiddleware(BaseMiddleware):
    """If the URL carries ?ticket=..., authenticate with it (once). Otherwise keep the session user."""

    async def __call__(self, scope, receive, send):
        scope = dict(scope)
        query = parse_qs(scope.get("query_string", b"").decode())
        ticket = (query.get("ticket") or [None])[0]
        if ticket:
            user_id = read_ticket(ticket)
            fresh = user_id is not None and await cache.aadd(f"ws-ticket-used:{ticket}", 1, TICKET_MAX_AGE_SECONDS * 2)
            scope["user"] = await _get_user(user_id) if fresh else AnonymousUser()
        return await super().__call__(scope, receive, send)

class OptionalOriginValidator(OriginValidator):
    """Browsers always send an Origin header, so we check it. Native mobile apps send none, so we allow
    a missing Origin; those clients authenticate with tickets, which a malicious website cannot obtain."""

    def valid_origin(self, parsed_origin):
        if parsed_origin is None:
            return True
        return super().valid_origin(parsed_origin)
