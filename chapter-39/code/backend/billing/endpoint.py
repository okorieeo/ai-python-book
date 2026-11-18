"""
The webhook endpoint's decisions as a plain function: bytes in, (status, body) out.
The Django view (views.py) only reads request.body and headers and calls this, so every branch is testable
without a web framework, and a real HTTP test needs nothing but the standard library.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Mapping

from .webhooks import (DEFAULT_TOLERANCE, Handler, IdempotencyStore, MalformedEvent, SignatureError, process_event,
                       verify_paystack_signature, verify_stripe_signature)

logger = logging.getLogger("billing.webhooks")


@dataclass(frozen=True)
class WebhookConfig:
    stripe_secrets: tuple[str, ...] = ()
    paystack_secret: str | None = None
    tolerance: int = DEFAULT_TOLERANCE
    max_body_bytes: int = 1_000_000


def handle_webhook_request(provider: str, headers: Mapping[str, str], body: bytes, *, config: WebhookConfig,
                           store: IdempotencyStore, handlers: Mapping[str, Handler], now: float) -> tuple[int, dict]:
    if provider not in ("stripe", "paystack"):
        return 404, {"error": "unknown provider"}
    if len(body) > config.max_body_bytes:
        return 413, {"error": "payload too large"}
    h = {k.lower(): v for k, v in headers.items()}       # header names are case-insensitive

    # 1. Authenticate FIRST, on the exact bytes received. Parsing before verifying breaks the signature.
    try:
        if provider == "stripe":
            verify_stripe_signature(body, h.get("stripe-signature"), config.stripe_secrets, now=now, tolerance=config.tolerance)
        else:
            if not config.paystack_secret:
                return 500, {"error": "provider not configured"}
            verify_paystack_signature(body, h.get("x-paystack-signature"), config.paystack_secret)
    except SignatureError as exc:
        logger.warning("webhook rejected", extra={"provider": provider, "reason": str(exc)})   # reason: log it, never return it
        return 400, {"error": "invalid signature"}

    # 2. Only now is the body trusted enough to parse.
    try:
        event = json.loads(body)
        if not isinstance(event, dict):
            raise ValueError("not an object")
    except ValueError:
        return 400, {"error": "malformed payload"}

    # 3. Process once. A failure is a 500 so the provider retries; everything else is a 200.
    try:
        outcome = process_event(provider, event, store, handlers)  # type: ignore[arg-type]
    except MalformedEvent:
        return 400, {"error": "malformed event"}
    except Exception:
        logger.exception("webhook handler failed", extra={"provider": provider})
        return 500, {"error": "handler failed"}
    return 200, {"status": outcome}
