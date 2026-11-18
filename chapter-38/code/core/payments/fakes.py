"""A fake gateway for tests and local development. It behaves like a real one without any network."""
from __future__ import annotations

import hashlib
import hmac
import json

from .gateway import (CheckoutRequest, CheckoutResult, EventType, GatewayRejected, GatewayUncertain,
                      NormalizedEvent, PaymentGateway, RefundResult, SignatureError, VerifiedPayment)
from .money import Money


class FakeGateway(PaymentGateway):
    def __init__(self, code: str, currencies: set[str], *, mode: str = "ok", secret: str = "whsec_fake"):
        self.code = code
        self.currencies = frozenset(currencies)
        self.mode = mode            # ok | reject | uncertain
        self.secret = secret
        self.sessions: dict[str, CheckoutRequest] = {}
        self.refunds: dict[str, RefundResult] = {}
        self.calls = 0

    def create_checkout(self, request: CheckoutRequest) -> CheckoutResult:
        self.calls += 1
        if self.mode == "reject":
            raise GatewayRejected("fake: rejected")
        if self.mode == "uncertain":
            raise GatewayUncertain("fake: timeout")
        if request.idempotency_key in self.sessions:                 # real gateways dedupe by key too
            ref = self.sessions[request.idempotency_key].reference
        else:
            self.sessions[request.idempotency_key] = request
            ref = request.reference
        return CheckoutResult(self.code, f"{self.code}_sess_{ref}", f"https://{self.code}.test/pay/{ref}")

    def verify(self, reference: str, provider_ref: str = "") -> VerifiedPayment:
        for request in self.sessions.values():
            if request.reference == reference:
                return VerifiedPayment(reference, "succeeded", request.amount, f"{self.code}_{reference}")
        raise GatewayRejected("unknown reference")

    def refund(self, *, reference: str, provider_ref: str, amount: Money, idempotency_key: str) -> RefundResult:
        if idempotency_key not in self.refunds:
            self.refunds[idempotency_key] = RefundResult(f"re_{len(self.refunds) + 1}", "succeeded", amount)
        return self.refunds[idempotency_key]

    def sign(self, raw: bytes) -> str:
        return hmac.new(self.secret.encode(), raw, hashlib.sha256).hexdigest()

    def verify_webhook(self, raw_body: bytes, headers: dict[str, str], *, now: int) -> None:
        if not hmac.compare_digest(self.sign(raw_body), headers.get("x-fake-signature", "")):
            raise SignatureError("bad signature")

    def parse_webhook(self, raw_body: bytes) -> NormalizedEvent:
        body = json.loads(raw_body)
        return NormalizedEvent(self.code, body["id"], EventType(body["type"]), body.get("reference", ""),
                               amount_minor=body.get("amount"), currency=body.get("currency"))
