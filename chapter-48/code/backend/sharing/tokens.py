"""Share-link tokens: framework-independent, so it runs and tests without Django.

Design (see section 48.9):
  * The link contains a long random token. Only its SHA-256 hash is stored.
    A database leak therefore does not hand out working links.
  * Tokens are compared in constant time.
  * Expiry is computed here, in one place, so the API, the Celery cleanup task
    and the tests all agree.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

TOKEN_BYTES = 32                      # 256 bits of randomness, 43 URL-safe characters
EXPIRY_CHOICES = {                    # the values the API accepts for "expires_in"
    "1d": timedelta(days=1),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
    "never": None,
}
DEFAULT_EXPIRY = "7d"


class InvalidExpiry(ValueError):
    """The caller asked for an expiry we do not offer."""


@dataclass(frozen=True)
class NewToken:
    raw: str          # shown to the user ONCE, never stored
    digest: str       # stored in the database (64 hex characters)


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def generate_token() -> NewToken:
    raw = secrets.token_urlsafe(TOKEN_BYTES)
    return NewToken(raw=raw, digest=hash_token(raw))


def token_matches(raw: str, stored_digest: str) -> bool:
    """Constant-time comparison of a presented token with a stored digest."""
    return hmac.compare_digest(hash_token(raw), stored_digest)


def expiry_from_choice(choice: str | None, *, now: datetime | None = None) -> datetime | None:
    """Turn an API value such as "7d" into a timestamp (None means never expires)."""
    choice = choice or DEFAULT_EXPIRY
    if choice not in EXPIRY_CHOICES:
        raise InvalidExpiry(f"expires_in must be one of {sorted(EXPIRY_CHOICES)}")
    delta = EXPIRY_CHOICES[choice]
    if delta is None:
        return None
    return (now or datetime.now(timezone.utc)) + delta


def link_state(
    *, expires_at: datetime | None, revoked_at: datetime | None, now: datetime | None = None
) -> str:
    """Return "active", "expired" or "revoked". Revoked wins over expired."""
    now = now or datetime.now(timezone.utc)
    if revoked_at is not None:
        return "revoked"
    if expires_at is not None and expires_at <= now:
        return "expired"
    return "active"


def public_url(base_url: str, raw_token: str) -> str:
    """Build the URL people open. The token goes in the path, never in a query string,
    so it is not copied into analytics tools that record query parameters."""
    return f"{base_url.rstrip('/')}/s/{raw_token}"
