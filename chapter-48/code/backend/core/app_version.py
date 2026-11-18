"""Minimum supported mobile app version (section 48.6).

Old app builds stay installed for months. When a breaking API change cannot be avoided, the
server can ask old builds to update instead of failing in confusing ways. The mobile app
sends its version in an `X-App-Version` header; the server compares it with a minimum.

Framework-independent on purpose: the middleware or DRF permission that calls it is three lines.
"""
from __future__ import annotations

import re

_VERSION = re.compile(r"^(\d{1,4})\.(\d{1,4})(?:\.(\d{1,4}))?(?:[-+].*)?$")


class BadVersion(ValueError):
    pass


def parse_version(text: str) -> tuple[int, int, int]:
    """'1.4' -> (1, 4, 0); '2.0.1-beta.3' -> (2, 0, 1). Anything else raises BadVersion."""
    m = _VERSION.match((text or "").strip())
    if not m:
        raise BadVersion(f"not a version: {text!r}")
    major, minor, patch = m.groups()
    return int(major), int(minor), int(patch or 0)


def needs_update(header_value: str | None, minimum: str) -> bool:
    """True only when the client SAID it is older than the minimum.

    A missing or unreadable header returns False: browsers and old builds that never sent
    the header must keep working. (Fail open is right here; this is a courtesy, not security.)
    """
    if not header_value:
        return False
    try:
        return parse_version(header_value) < parse_version(minimum)
    except BadVersion:
        return False
