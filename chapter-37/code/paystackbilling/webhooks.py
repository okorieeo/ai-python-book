"""Receiving Paystack webhooks: verify the signature, ignore duplicates, run one handler, answer correctly.

Three things make Paystack different from Stripe here:
  * The signature is HMAC-SHA512 (not SHA-256) of the raw body, keyed with your SECRET KEY. There is no
    separate webhook secret.
  * The signature has NO timestamp, so a captured request stays valid forever. Replays must be stopped
    by remembering what we already processed.
  * Events have NO id. Paystack resends the identical body, so we identify an event by a hash of its bytes.
"""
import hashlib
import hmac
import json
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from .errors import SignatureError, UnresolvedCustomer

# Paystack documents these as the only addresses webhooks come from (test and live). Treat the list as
# defence in depth, never as the main check, and look at the current documentation before you rely on it.
PAYSTACK_IPS = frozenset({"52.31.139.75", "52.49.173.169", "52.214.14.220"})


def sign_body(body: bytes, secret_key: str) -> str:
    """The x-paystack-signature value for a body. Used by tests and the simulator, never by production code."""
    return hmac.new(secret_key.encode("utf-8"), body, hashlib.sha512).hexdigest()


def event_key(body: bytes) -> str:
    """Identify an event by its exact bytes. Retries are byte-for-byte identical, so this finds duplicates."""
    return hashlib.sha256(body).hexdigest()


class PaystackVerifier:
    def __init__(self, secret_key: str):
        if not secret_key.startswith(("sk_test_", "sk_live_")):
            raise ValueError("Webhooks are signed with your secret key (sk_test_... or sk_live_...).")
        self._key = secret_key

    def verify(self, body: bytes, signature: str) -> dict:
        if not signature:
            raise SignatureError("Missing x-paystack-signature header.")
        expected = sign_body(body, self._key)
        if not hmac.compare_digest(expected, signature.strip().lower()):
            raise SignatureError("The signature does not match the body.")
        try:
            event = json.loads(body)
        except ValueError:
            raise SignatureError("The body is not valid JSON.") from None
        if not isinstance(event, dict) or "event" not in event:
            raise SignatureError("The body is not a Paystack event.")
        return event


def source_ip_allowed(remote_addr: str, forwarded_for: str = "", *, trust_proxy: bool = False,
                      allowed=PAYSTACK_IPS) -> bool:
    """Optional extra check. Behind a load balancer the real address is in X-Forwarded-For, but that header
    can be forged by anyone who reaches you directly, so only read it when you run behind a proxy you control."""
    ip = remote_addr
    if trust_proxy and forwarded_for:
        ip = forwarded_for.split(",")[0].strip()
    return ip in allowed


@dataclass
class WebhookResult:
    status: int
    outcome: str
    event_type: Optional[str] = None
    warnings: list = field(default_factory=list)


class WebhookProcessor:
    """Runs each distinct event at most once and tells Paystack whether to retry.

    HTTP answers: 200 means done, do not resend. Anything else makes Paystack retry (live mode: every
    3 minutes for four tries, then hourly for up to 72 hours). So: 400 bad signature, 409 busy, 500 failed,
    and 200 for processed, duplicate, ignored and wrong-mode events.
    """

    def __init__(self, verifier, store, handlers: dict, *, livemode: bool, clock: Callable = time.time,
                 lease_seconds: int = 300, log: Callable = lambda *a: None):
        self.verifier, self.store, self.handlers = verifier, store, handlers
        self.livemode, self.clock, self.lease_seconds, self.log = livemode, clock, lease_seconds, log

    def handle(self, body: bytes, signature: str) -> WebhookResult:
        try:
            event = self.verifier.verify(body, signature)
        except SignatureError as error:
            self.log("webhook_rejected", str(error))
            return WebhookResult(400, "bad_signature")
        return self.process_verified(event, event_key(body))

    def process_verified(self, event: dict, key: str) -> WebhookResult:
        name = event["event"]
        data = event.get("data")
        domain = data.get("domain") if isinstance(data, dict) else None
        if domain and (domain == "live") != self.livemode:
            self.log("webhook_wrong_mode", name)
            return WebhookResult(200, "ignored_wrong_mode", name)
        claim = self.store.begin_event(key, name, self.clock(), self.lease_seconds)
        if claim == "duplicate":
            return WebhookResult(200, "duplicate", name)
        if claim == "busy":
            return WebhookResult(409, "busy", name)
        handler = self.handlers.get(name)
        if handler is None:
            self.store.finish_event(key, "ignored")
            return WebhookResult(200, "ignored", name)
        try:
            handler(event)
        except UnresolvedCustomer as error:
            self.store.finish_event(key, "failed", str(error))
            return WebhookResult(500, "retry_unresolved_customer", name)
        except Exception as error:
            self.store.finish_event(key, "failed", f"{type(error).__name__}: {error}")
            self.log("webhook_handler_failed", name, type(error).__name__)
            return WebhookResult(500, "handler_failed", name)
        self.store.finish_event(key, "processed")
        return WebhookResult(200, "processed", name)
