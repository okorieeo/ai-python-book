"""Receiving Stripe webhooks: verify the signature, ignore duplicates, run one handler, answer correctly."""
import hashlib
import hmac
import json
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from .errors import SignatureError, UnresolvedCustomer

DEFAULT_TOLERANCE = 300     # seconds: how old a signed timestamp may be


def sign_payload(payload: bytes, secret: str, timestamp: int) -> str:
    """Build a Stripe-Signature header value. Used by tests and the simulator, never by production code."""
    mac = hmac.new(secret.encode("utf-8"), f"{timestamp}.".encode("utf-8") + payload, hashlib.sha256)
    return f"t={timestamp},v1={mac.hexdigest()}"


class ManualVerifier:
    """Checks the Stripe-Signature header the way Stripe documents it, with no SDK needed.

    The header looks like  t=1700000000,v1=<hex>,v1=<hex>  where each v1 is HMAC-SHA256 of
    "<t>.<raw body>" using an endpoint's signing secret. Several v1 values appear while a secret is
    being rotated, so we accept a match against any of them. The timestamp must be recent, which stops
    someone replaying an old, genuinely signed request.
    """

    def __init__(self, secrets, tolerance: int = DEFAULT_TOLERANCE, clock: Callable = time.time):
        self.secrets = (secrets,) if isinstance(secrets, str) else tuple(secrets)
        if not self.secrets or not all(s.startswith("whsec_") for s in self.secrets):
            raise ValueError("Webhook signing secrets start with whsec_.")
        self.tolerance, self.clock = tolerance, clock

    def verify(self, payload: bytes, header: str) -> dict:
        if not header:
            raise SignatureError("Missing Stripe-Signature header.")
        timestamp, signatures = None, []
        for part in header.split(","):
            key, _, value = part.strip().partition("=")
            if key == "t":
                try:
                    timestamp = int(value)
                except ValueError:
                    raise SignatureError("Bad timestamp in the signature header.") from None
            elif key == "v1":
                signatures.append(value)
        if timestamp is None or not signatures:
            raise SignatureError("The signature header has no timestamp or no v1 signature.")
        signed = f"{timestamp}.".encode("utf-8") + payload
        expected = [hmac.new(s.encode("utf-8"), signed, hashlib.sha256).hexdigest() for s in self.secrets]
        if not any(hmac.compare_digest(e, got) for e in expected for got in signatures):
            raise SignatureError("No signature matches the payload.")
        if abs(self.clock() - timestamp) > self.tolerance:
            raise SignatureError("The signature timestamp is outside the tolerance.")
        try:
            return json.loads(payload)
        except ValueError:
            raise SignatureError("The payload is not valid JSON.") from None


class OfficialVerifier:
    """Verifies with Stripe's own library, then reads the JSON ourselves (needs the stripe package).

    Use this in production if you prefer the vendor's code. It is not run in this chapter's tests.
    """

    def __init__(self, secret: str, tolerance: int = DEFAULT_TOLERANCE):
        import stripe

        self._stripe, self._secret, self._tolerance = stripe, secret, tolerance

    def verify(self, payload: bytes, header: str) -> dict:
        try:
            self._stripe.Webhook.construct_event(payload, header, self._secret, self._tolerance)
        except (self._stripe.SignatureVerificationError, ValueError) as error:
            raise SignatureError(str(error)) from error
        return json.loads(payload)


@dataclass
class WebhookResult:
    status: int                       # the HTTP status to answer with
    outcome: str                      # a short word for logs: processed, duplicate, ignored, ...
    event_id: Optional[str] = None
    warnings: list = field(default_factory=list)


class WebhookProcessor:
    """Runs one event at most once and tells Stripe whether to retry.

    HTTP answers: 2xx means "got it, do not send again". Anything else makes Stripe retry later, with
    growing delays, for days. So we answer:
      400  the signature is bad (do not retry; someone is guessing, or the secret is wrong)
      409  another worker is processing this event right now (retry later)
      500  our handler failed (retry later)
      200  processed, a duplicate, an unknown event type, or an event from the wrong mode
    """

    def __init__(self, verifier, store, handlers: dict, *, livemode: bool, expected_api_version: str = "",
                 clock: Callable = time.time, lease_seconds: int = 300, log: Callable = lambda *a: None):
        self.verifier, self.store, self.handlers = verifier, store, handlers
        self.livemode, self.expected_api_version = livemode, expected_api_version
        self.clock, self.lease_seconds, self.log = clock, lease_seconds, log

    def handle(self, payload: bytes, header: str) -> WebhookResult:
        try:
            event = self.verifier.verify(payload, header)
        except SignatureError as error:
            self.log("webhook_rejected", str(error))
            return WebhookResult(400, "bad_signature")
        return self.process_verified(event)

    def process_verified(self, event: dict) -> WebhookResult:
        """Run an event whose authenticity is already established: a verified delivery, or a replay
        of an event fetched from Stripe's API with our own secret key."""
        event_id, event_type = event["id"], event["type"]
        warnings = []
        if self.expected_api_version and event.get("api_version") != self.expected_api_version:
            warnings.append(f"event api_version {event.get('api_version')} differs from {self.expected_api_version}")
        if bool(event.get("livemode")) != self.livemode:
            self.log("webhook_wrong_mode", event_id)
            return WebhookResult(200, "ignored_wrong_mode", event_id, warnings)

        claim = self.store.begin_event(event_id, event_type, self.clock(), self.lease_seconds)
        if claim == "duplicate":
            return WebhookResult(200, "duplicate", event_id, warnings)
        if claim == "busy":
            return WebhookResult(409, "busy", event_id, warnings)

        handler = self.handlers.get(event_type)
        if handler is None:
            self.store.finish_event(event_id, "ignored")
            return WebhookResult(200, "ignored", event_id, warnings)
        try:
            handler(event)
        except UnresolvedCustomer as error:          # a normal ordering problem: try again later
            self.store.finish_event(event_id, "failed", str(error))
            return WebhookResult(500, "retry_unresolved_customer", event_id, warnings)
        except Exception as error:                   # a bug or an outage: record it and let Stripe retry
            self.store.finish_event(event_id, "failed", f"{type(error).__name__}: {error}")
            self.log("webhook_handler_failed", event_id, type(error).__name__)
            return WebhookResult(500, "handler_failed", event_id, warnings)
        self.store.finish_event(event_id, "processed")
        return WebhookResult(200, "processed", event_id, warnings)
