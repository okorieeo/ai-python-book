"""The root-cause fix: compare aware datetimes with aware datetimes, and refuse naive input."""
from datetime import datetime, timezone


def is_expired(expires_at, now=None):
    if expires_at.tzinfo is None:
        raise ValueError("expires_at must be timezone-aware (store and compare UTC)")
    now = now or datetime.now(timezone.utc)
    return expires_at <= now
