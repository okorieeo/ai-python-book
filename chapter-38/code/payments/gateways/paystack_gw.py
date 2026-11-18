"""Paystack adapter over plain HTTPS (Chapter 37 shows the same calls with its client class)."""
from datetime import datetime

import requests
from django.conf import settings

from core.payments import normalize
from core.payments.gateway import (CheckoutRequest, CheckoutResult, GatewayRejected, GatewayUncertain, PaymentGateway,
                                   RefundResult, SignatureError, VerifiedPayment)
from core.payments.money import Money
from core.payments.reconciliation import Line
from core.payments.webhooks import is_paystack_ip, verify_paystack_signature

BASE = "https://api.paystack.co"
TIMEOUT = (3.05, 10)          # connect, read: never call a payment API without a timeout


class PaystackGateway(PaymentGateway):
    code = "paystack"
    currencies = frozenset({"NGN", "GHS", "ZAR", "KES", "USD"})     # what your account has enabled may be fewer

    def __init__(self):
        self.secret = settings.PAYSTACK_SECRET_KEY                 # sk_test_... or sk_live_..., from the environment
        self.check_ip = getattr(settings, "PAYSTACK_CHECK_WEBHOOK_IP", True)

    def _call(self, method: str, path: str, **kwargs):
        try:
            response = requests.request(method, BASE + path, headers={"Authorization": f"Bearer {self.secret}"},
                                        timeout=TIMEOUT, **kwargs)
        except (requests.ConnectTimeout, requests.ConnectionError) as exc:
            raise GatewayUncertain(type(exc).__name__) from exc    # may have reached Paystack: stay on this gateway
        except requests.ReadTimeout as exc:
            raise GatewayUncertain("ReadTimeout") from exc
        if response.status_code >= 500 or response.status_code == 429:
            raise GatewayUncertain(f"HTTP {response.status_code}")
        if response.status_code >= 400:
            raise GatewayRejected(response.text[:200])
        return response.json()

    def create_checkout(self, request: CheckoutRequest) -> CheckoutResult:
        body = self._call("POST", "/transaction/initialize", json={
            "email": request.email, "amount": request.amount.amount_minor, "currency": request.amount.currency,
            "reference": request.reference, "callback_url": request.success_url,
            "metadata": {"payment_reference": request.reference}})
        data = body["data"]
        return CheckoutResult(self.code, data["access_code"], data["authorization_url"])

    def verify(self, reference: str, provider_ref: str = "") -> VerifiedPayment:
        data = self._call("GET", f"/transaction/verify/{reference}")["data"]
        status = {"success": "succeeded", "failed": "failed", "abandoned": "failed"}.get(data["status"], "pending")
        return VerifiedPayment(reference, status, Money(data["amount"], data["currency"]), str(data["id"]))

    def refund(self, *, reference: str, provider_ref: str, amount: Money, idempotency_key: str) -> RefundResult:
        # Paystack takes the transaction reference. We make our own Refund row unique per request (key above).
        data = self._call("POST", "/refund", json={"transaction": reference, "amount": amount.amount_minor})["data"]
        return RefundResult(str(data.get("id", "")), "pending", amount)    # final state arrives as refund.processed

    def list_transactions(self, start: datetime, end: datetime) -> list:
        lines, page = [], 1
        while True:
            body = self._call("GET", "/transaction", params={"status": "success", "perPage": 100, "page": page,
                                                              "from": start.isoformat(), "to": end.isoformat()})
            for tx in body["data"]:
                lines.append(Line(tx["reference"], tx["amount"], tx["currency"], "succeeded",
                                  fee_minor=tx.get("fees") or 0))
            if page >= (body.get("meta") or {}).get("pageCount", 1):
                return lines
            page += 1

    def verify_webhook(self, raw_body: bytes, headers: dict, *, now: int) -> None:
        verify_paystack_signature(raw_body, headers.get("x-paystack-signature", ""), self.secret)
        client_ip = headers.get("x-client-ip", "")                 # set by YOUR trusted proxy logic (Chapter 17)
        if self.check_ip and client_ip and not is_paystack_ip(client_ip):
            raise SignatureError("request did not come from a Paystack address")

    def parse_webhook(self, raw_body: bytes):
        return normalize.parse_paystack(raw_body)
