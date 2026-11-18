"""The quick patch: make the crash go away. The test below shows what it costs."""
from datetime import datetime


def is_expired(expires_at, now=None):
    now = now or datetime.now()
    return expires_at.replace(tzinfo=None) <= now    # silences the TypeError, compares UTC with local time
