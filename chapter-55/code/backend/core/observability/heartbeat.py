"""Dead-man's-switch pings: tell an outside service "I ran", so silence raises an alarm.

Works with Healthchecks.io-style URLs: URL (success), URL/start, URL/fail. A ping URL is
a capability: anyone who knows it can fake a success, so keep it in .env like a secret
and never log it. Monitoring must never break the job it watches: nothing here raises.
"""
from __future__ import annotations

import logging
import urllib.request
from contextlib import contextmanager

log = logging.getLogger("heartbeat")


def ping(url: str | None, suffix: str = "", *, timeout: float = 5.0,
         require_https: bool = True, opener=urllib.request.urlopen) -> bool:
    if not url:
        return False
    if require_https and not url.startswith("https://"):
        log.warning("heartbeat url is not https; not sent",
                    extra={"event": "heartbeat_skipped"})
        return False
    request = urllib.request.Request(
        url.rstrip("/") + suffix, headers={"User-Agent": "ai-chat-heartbeat"}
    )
    try:
        with opener(request, timeout=timeout) as response:
            return 200 <= response.status < 300
    except Exception:  # noqa: BLE001 - never let monitoring break the job
        log.warning("heartbeat ping failed", extra={"event": "heartbeat_failed"})
        return False


@contextmanager
def heartbeat(url: str | None, **kwargs):
    """with heartbeat(url): do_work()  ->  /start, then success or /fail."""
    ping(url, "/start", **kwargs)
    try:
        yield
    except BaseException:
        ping(url, "/fail", **kwargs)
        raise
    else:
        ping(url, **kwargs)
