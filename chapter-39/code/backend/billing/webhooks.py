"""
Payment webhooks, framework-free: verify who sent it, decide whether we have seen it, run the handler.

In production you may prefer the provider's own library for the Stripe check (`stripe.Webhook.construct_event`).
We implement both schemes by hand here for one reason: so the tests can SIGN requests the way the provider does,
and prove that tampered, stale, replayed and duplicated deliveries are all handled. Know what the library does.
"""
from __future__ import annotations

import hashlib
import hmac
from typing import Callable, Literal, Mapping, Protocol, Sequence

DEFAULT_TOLERANCE = 300          # seconds. Stripe's libraries default to five minutes


class SignatureError(Exception):
    """The request did not come from the provider, or was altered or replayed. Becomes HTTP 400."""


class MalformedEvent(ValueError):
    """Correctly signed, but not shaped like an event we understand. Becomes HTTP 400."""


# ------------------------------------------------------------------------------ Stripe
def compute_stripe_signature(secret: str, timestamp: int, payload: bytes) -> str:
    """HMAC-SHA256 over '<timestamp>.<raw body>', hex-encoded, keyed with the endpoint secret (whsec_...)."""
    signed = str(timestamp).encode() + b"." + payload
    return hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()


def verify_stripe_signature(payload: bytes, header: str | None, secrets: Sequence[str], *, now: float,
                            tolerance: int = DEFAULT_TOLERANCE) -> int:
    """
    Header looks like  t=1700000000,v1=<hex>[,v1=<hex>]  . Several v1 values appear while a secret is being
    rotated, so a match against ANY of our secrets is enough. Other schemes (Stripe adds a fake v0 to test
    events) are ignored on purpose: accepting them would let an attacker choose a weaker scheme.
    Returns the signed timestamp.
    """
    if not header:
        raise SignatureError("missing Stripe-Signature header")
    timestamp: int | None = None
    candidates: list[str] = []
    for part in header.split(","):
        key, _, value = part.strip().partition("=")
        if key == "t":
            try:
                timestamp = int(value)
            except ValueError:
                raise SignatureError("timestamp is not a number") from None
        elif key == "v1" and value:
            candidates.append(value)
    if timestamp is None:
        raise SignatureError("no timestamp in header")
    if not candidates:
        raise SignatureError("no v1 signature in header")
    if abs(now - timestamp) > tolerance:                # too old (replay) OR too far in the future (clock trick)
        raise SignatureError("timestamp outside the tolerance window")
    for secret in secrets:
        expected = compute_stripe_signature(secret, timestamp, payload)
        for candidate in candidates:
            if hmac.compare_digest(expected, candidate):   # constant time: no hint about how much matched
                return timestamp
    raise SignatureError("no matching signature")


# ------------------------------------------------------------------------------ Paystack
def compute_paystack_signature(secret: str, payload: bytes) -> str:
    """HMAC-SHA512 over the raw body, hex-encoded, keyed with your SECRET API key. No timestamp is signed."""
    return hmac.new(secret.encode(), payload, hashlib.sha512).hexdigest()


def verify_paystack_signature(payload: bytes, header: str | None, secret: str) -> None:
    if not header:
        raise SignatureError("missing x-paystack-signature header")
    expected = compute_paystack_signature(secret, payload)
    if not hmac.compare_digest(expected, header.strip().lower()):
        raise SignatureError("no matching signature")


# ------------------------------------------------------------------------------ events
Provider = Literal["stripe", "paystack"]
Outcome = Literal["processed", "duplicate", "ignored"]


def event_type(provider: Provider, event: Mapping) -> str:
    key = "type" if provider == "stripe" else "event"
    value = event.get(key)
    if not isinstance(value, str) or not value:
        raise MalformedEvent(f"event has no {key!r}")
    return value


def event_key(provider: Provider, event: Mapping) -> str:
    """
    A stable identity for 'this exact event', used to ignore redeliveries.
    Stripe gives every event an id. Paystack events have NO top-level id and its signature carries no timestamp,
    so we build one from the event name plus the transaction's own id (or reference). Idempotency is also
    Paystack's only defence against a replayed delivery.
    """
    if provider == "stripe":
        eid = event.get("id")
        if not isinstance(eid, str) or not eid:
            raise MalformedEvent("stripe event has no id")
        return f"stripe:{eid}"
    data = event.get("data")
    if not isinstance(data, Mapping):
        raise MalformedEvent("paystack event has no data object")
    ident = data.get("id") or data.get("reference")
    if ident in (None, ""):
        raise MalformedEvent("paystack event has neither data.id nor data.reference")
    return f"paystack:{event_type('paystack', event)}:{ident}"


class IdempotencyStore(Protocol):
    def claim(self, key: str) -> bool: ...      # True the first time, False if already claimed
    def release(self, key: str) -> None: ...    # forget a claim (the handler failed, so a retry must run again)


class MemoryIdempotencyStore:
    def __init__(self) -> None:
        self._claimed: set[str] = set()

    def claim(self, key: str) -> bool:
        if key in self._claimed:
            return False
        self._claimed.add(key)
        return True

    def release(self, key: str) -> None:
        self._claimed.discard(key)


Handler = Callable[[dict], None]


def process_event(provider: Provider, event: dict, store: IdempotencyStore, handlers: Mapping[str, Handler]) -> Outcome:
    """
    ignored    : an event type we do not handle. Still answered 200, or the provider retries it for days.
    duplicate  : already processed. Answered 200 with no side effects.
    processed  : the handler ran.
    If the handler raises, the claim is released and the error propagates, so the endpoint answers 500, the
    provider redelivers, and the work is attempted again instead of being silently lost.
    """
    handler = handlers.get(event_type(provider, event))
    if handler is None:
        return "ignored"
    key = event_key(provider, event)
    if not store.claim(key):
        return "duplicate"
    try:
        handler(event)
    except Exception:
        store.release(key)
        raise
    return "processed"
