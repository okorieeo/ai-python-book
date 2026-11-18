"""Signature checks and once-only processing for webhook deliveries."""
from __future__ import annotations

import hashlib
import hmac
from typing import Callable, Protocol

from .gateway import NormalizedEvent, SignatureError

STRIPE_TOLERANCE_SECONDS = 300
PAYSTACK_IPS = frozenset({"52.31.139.75", "52.49.173.169", "52.214.14.220"})   # per Paystack docs, re-check


def verify_stripe_signature(raw_body: bytes, header: str, secret: str, *, now: int,
                            tolerance: int = STRIPE_TOLERANCE_SECONDS) -> None:
    """Stripe-Signature: t=<unix>,v1=<hex>[,v1=<hex>]. HMAC-SHA256 over b"<t>." + raw body."""
    if not header or not secret:
        raise SignatureError("missing signature or secret")
    timestamp, candidates = None, []
    for part in header.split(","):
        key, _, value = part.strip().partition("=")
        if key == "t":
            timestamp = value
        elif key == "v1":
            candidates.append(value)
    if timestamp is None or not timestamp.isdigit() or not candidates:
        raise SignatureError("malformed Stripe-Signature header")
    expected = hmac.new(secret.encode(), timestamp.encode() + b"." + raw_body, hashlib.sha256).hexdigest()
    if not any(hmac.compare_digest(expected, c) for c in candidates):
        raise SignatureError("signature mismatch")
    if abs(now - int(timestamp)) > tolerance:
        raise SignatureError("timestamp outside tolerance (possible replay)")


def verify_paystack_signature(raw_body: bytes, signature: str, secret: str) -> None:
    """x-paystack-signature: hex HMAC-SHA512 of the raw body, keyed with your secret key."""
    if not signature or not secret:
        raise SignatureError("missing signature or secret")
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha512).hexdigest()
    if not hmac.compare_digest(expected, signature.strip().lower()):
        raise SignatureError("signature mismatch")


def is_paystack_ip(ip: str, allowed: frozenset[str] = PAYSTACK_IPS) -> bool:
    """Optional second layer. Pass the client IP resolved by your trusted-proxy logic (Chapter 17)."""
    return ip in allowed


class Deduper(Protocol):
    def claim(self, provider: str, event_id: str) -> bool:
        """True the first time, False for a repeat."""

    def release(self, provider: str, event_id: str) -> None:
        """Undo a claim so a failed event can be retried."""


class InMemoryDeduper:
    def __init__(self):
        self._seen: set[tuple[str, str]] = set()

    def claim(self, provider: str, event_id: str) -> bool:
        key = (provider, event_id)
        if key in self._seen:
            return False
        self._seen.add(key)
        return True

    def release(self, provider: str, event_id: str) -> None:
        self._seen.discard((provider, event_id))


def process_once(event: NormalizedEvent, deduper: Deduper, handler: Callable[[NormalizedEvent], None]) -> str:
    """Run handler at most once per event. A crash releases the claim so the gateway's retry works."""
    if not deduper.claim(event.provider, event.event_id):
        return "duplicate"
    try:
        handler(event)
    except Exception:
        deduper.release(event.provider, event.event_id)
        raise
    return "processed"
