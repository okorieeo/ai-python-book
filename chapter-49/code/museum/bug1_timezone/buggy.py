"""Bug 1: a share link's expiry check. Crashes with a TypeError as soon as it meets a real database value."""
from datetime import datetime


def is_expired(expires_at, now=None):
    now = now or datetime.now()          # naive local time
    return expires_at <= now             # expires_at comes from the database, timezone-aware
