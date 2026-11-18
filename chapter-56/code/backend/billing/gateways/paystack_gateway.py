from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from datetime import datetime, timezone

import httpx
from django.conf import settings

from .base import BillingEvent, CheckoutSession, GatewayError, InvalidSignature

API = "https://api.paystack.co"


def _dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class PaystackGateway:
    code = "paystack"

    def __init__(self, *, client: httpx.Client | None = None):
        self._http = client or httpx.Client(base_url=API, timeout=15.0)

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}"}

    def create_checkout(self, *, user, plan, success_url, cancel_url) -> CheckoutSession:
        if not plan.paystack_plan_code or not plan.paystack_amount_minor:
            raise GatewayError(f"Plan {plan.code} is not configured for Paystack.")
        payload = {
            "email": user.email,
            "amount": plan.paystack_amount_minor,  # overridden by the plan's own amount, but required
            "currency": settings.PAYSTACK_CURRENCY,
            "plan": plan.paystack_plan_code,  # makes this charge start a recurring subscription
            "reference": f"sub_{uuid.uuid4().hex}",
            "callback_url": success_url,
            "metadata": {"user_public_id": str(user.public_id), "plan_code": plan.code},
        }
        try:
            response = self._http.post("/transaction/initialize", json=payload, headers=self._headers())
            response.raise_for_status()
            data = response.json()["data"]
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            raise GatewayError("Could not start checkout.") from exc
        return CheckoutSession(url=data["authorization_url"], reference=data["reference"])

    def parse_webhook(self, *, body, headers) -> BillingEvent | None:
        # HMAC-SHA512 (not SHA-256!) of the RAW body, keyed with the secret key, hex encoded.
        expected = hmac.new(settings.PAYSTACK_SECRET_KEY.encode(), body, hashlib.sha512).hexdigest()
        if not hmac.compare_digest(expected, headers.get("x-paystack-signature", "")):
            raise InvalidSignature("Bad Paystack signature.")
        event = json.loads(body)
        etype, data = event.get("event", ""), event.get("data") or {}
        customer = data.get("customer") or {}
        # Paystack sends no event id, so we build one from what identifies the thing that happened.
        ident = data.get("id") or data.get("reference") or data.get("subscription_code") or ""
        base = dict(provider="paystack", event_id=f"{etype}:{ident}", event_type=etype,
                    customer_email=customer.get("email"), external_customer_id=customer.get("customer_code") or "")

        if etype == "charge.success":
            meta = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
            plan = data.get("plan") if isinstance(data.get("plan"), dict) else {}
            if data.get("status") != "success":
                return None
            return BillingEvent(
                kind="ACTIVE", user_public_id=meta.get("user_public_id"), plan_code=meta.get("plan_code"),
                price_ref=plan.get("plan_code"), occurred_at=_dt(data.get("paid_at")),
                amount_minor=data.get("amount"), currency=data.get("currency"), **base)
        if etype == "subscription.create":
            plan = data.get("plan") or {}
            return BillingEvent(
                kind="ACTIVE", price_ref=plan.get("plan_code"), period_end=_dt(data.get("next_payment_date")),
                external_subscription_id=data.get("subscription_code") or "",
                occurred_at=_dt(data.get("createdAt")), **base)
        if etype == "invoice.payment_failed":
            sub = data.get("subscription") or {}
            return BillingEvent(kind="PAST_DUE", external_subscription_id=sub.get("subscription_code") or "", **base)
        if etype in {"subscription.not_renew", "subscription.disable"}:
            # Both mean "no more charges". The customer keeps what they paid for until the period ends.
            return BillingEvent(kind="ACTIVE", cancel_at_period_end=True,
                                external_subscription_id=data.get("subscription_code") or "",
                                period_end=_dt(data.get("next_payment_date")), **base)
        return None

    def manage_url(self, *, subscription, return_url) -> str:
        if not subscription.external_subscription_id:
            raise GatewayError("No Paystack subscription for this account.")
        try:
            response = self._http.get(f"/subscription/{subscription.external_subscription_id}/manage/link",
                                      headers=self._headers())
            response.raise_for_status()
            return response.json()["data"]["link"]
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            raise GatewayError("Could not open the subscription page.") from exc
