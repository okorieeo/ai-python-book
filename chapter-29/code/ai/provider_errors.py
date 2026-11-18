"""Translate provider HTTP statuses into our own errors. Pure and tested; the SDK adapter calls it."""
from __future__ import annotations

from .errors import (AIAuthError, AIBadRequest, AIBillingError, AIContextTooLong, AIError, AIOverloaded,
                     AIRateLimited, AIServerError, AITimeout)


def error_for_status(status: int, *, retry_after: int | None = None, request_id: str | None = None) -> AIError:
    kw = {"retry_after": retry_after, "request_id": request_id}
    if status == 429:
        return AIRateLimited(**kw)
    if status == 529:
        return AIOverloaded(**kw)
    if status == 504 or status == 408:
        return AITimeout(**kw)
    if status == 413:
        return AIContextTooLong(**kw)
    if status == 402:
        return AIBillingError(**kw)
    if status in (401, 403):
        return AIAuthError(**kw)
    if status >= 500:
        return AIServerError(**kw)
    return AIBadRequest(**kw)       # 400, 404, 409 and other 4xx: our request is wrong; do not retry


def parse_retry_after(value: str | None) -> int | None:
    """The Retry-After header as whole seconds, or None if absent or not a number."""
    try:
        seconds = int(float(value)) if value is not None else None
    except (TypeError, ValueError):
        return None
    return seconds if seconds is not None and seconds >= 0 else None
