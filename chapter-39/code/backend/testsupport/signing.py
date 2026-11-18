"""Build webhook requests exactly as the providers send them. Used by tests and by scripts/send_webhook.py."""
from __future__ import annotations

import json

from billing.webhooks import compute_paystack_signature, compute_stripe_signature


def to_bytes(event: dict) -> bytes:
    """Serialise ONCE and sign THOSE bytes. Re-serialising later would change spacing and break the signature."""
    return json.dumps(event, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def stripe_headers(payload: bytes, secret: str, timestamp: int) -> dict[str, str]:
    return {"Content-Type": "application/json",
            "Stripe-Signature": f"t={timestamp},v1={compute_stripe_signature(secret, timestamp, payload)}"}


def paystack_headers(payload: bytes, secret: str) -> dict[str, str]:
    return {"Content-Type": "application/json", "x-paystack-signature": compute_paystack_signature(secret, payload)}


def stripe_event(event_id: str, type_: str, obj: dict) -> dict:
    return {"id": event_id, "object": "event", "type": type_, "data": {"object": obj}}


def paystack_event(event: str, data: dict) -> dict:
    return {"event": event, "data": data}
