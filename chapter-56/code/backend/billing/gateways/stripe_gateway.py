from __future__ import annotations

import json
from datetime import datetime, timezone

import stripe
from django.conf import settings

from .base import BillingEvent, CheckoutSession, GatewayError, InvalidSignature


def _ts(value) -> datetime | None:
    return datetime.fromtimestamp(value, tz=timezone.utc) if value else None


def _item(subscription: dict) -> dict:
    items = (subscription.get("items") or {}).get("data") or []
    return items[0] if items else {}


def _period_end(subscription: dict) -> datetime | None:
    # Since API version 2025-03-31 (basil) the billing period lives on the subscription ITEM.
    # Older API versions still send it on the subscription itself, so accept both.
    return _ts(_item(subscription).get("current_period_end") or subscription.get("current_period_end"))


class StripeGateway:
    code = "stripe"

    def __init__(self, *, client=None):
        self._client = client or stripe.StripeClient(settings.STRIPE_SECRET_KEY)

    def create_checkout(self, *, user, plan, success_url, cancel_url) -> CheckoutSession:
        if not plan.stripe_price_id:
            raise GatewayError(f"Plan {plan.code} has no Stripe price configured.")
        meta = {"user_public_id": str(user.public_id), "plan_code": plan.code}
        params = {
            "mode": "subscription",
            "line_items": [{"price": plan.stripe_price_id, "quantity": 1}],
            "client_reference_id": str(user.public_id),
            "metadata": meta,
            "subscription_data": {"metadata": meta},  # copied onto the subscription itself
            "success_url": success_url,
            "cancel_url": cancel_url,
        }
        sub = getattr(user, "subscription", None)  # reverse one-to-one: None when the user never subscribed
        if sub and sub.gateway == "stripe" and sub.external_customer_id:
            params["customer"] = sub.external_customer_id
        else:
            params["customer_email"] = user.email
        try:
            session = self._client.v1.checkout.sessions.create(params=params)
        except stripe.StripeError as exc:
            raise GatewayError("Could not start checkout.") from exc
        return CheckoutSession(url=session.url, reference=session.id)

    def parse_webhook(self, *, body, headers) -> BillingEvent | None:
        signature = headers.get("stripe-signature", "")
        try:  # verifies the HMAC and rejects timestamps older than 5 minutes
            stripe.Webhook.construct_event(body, signature, settings.STRIPE_WEBHOOK_SECRET)
        except (stripe.SignatureVerificationError, ValueError) as exc:
            raise InvalidSignature("Bad Stripe signature.") from exc
        event = json.loads(body)
        obj = event["data"]["object"]
        etype = event["type"]
        base = dict(provider="stripe", event_id=event["id"], event_type=etype, occurred_at=_ts(event.get("created")))

        if etype == "checkout.session.completed":
            if obj.get("mode") != "subscription" or obj.get("payment_status") not in {"paid", "no_payment_required"}:
                return None
            meta = obj.get("metadata") or {}
            return BillingEvent(
                kind="ACTIVE", user_public_id=obj.get("client_reference_id") or meta.get("user_public_id"),
                customer_email=(obj.get("customer_details") or {}).get("email"), plan_code=meta.get("plan_code"),
                external_customer_id=obj.get("customer") or "", external_subscription_id=obj.get("subscription") or "",
                **base)

        if etype in {"customer.subscription.updated", "customer.subscription.deleted"}:
            status = obj.get("status")
            if etype.endswith("deleted") or status in {"canceled", "incomplete_expired"}:
                kind = "CANCELED"
            elif status in {"active", "trialing"}:
                kind = "ACTIVE"
            elif status in {"past_due", "unpaid"}:
                kind = "PAST_DUE"
            else:
                return None  # incomplete, paused...: nothing to change yet
            meta = obj.get("metadata") or {}
            return BillingEvent(
                kind=kind, user_public_id=meta.get("user_public_id"), plan_code=meta.get("plan_code"),
                price_ref=(_item(obj).get("price") or {}).get("id"), external_customer_id=obj.get("customer") or "",
                external_subscription_id=obj.get("id") or "", period_end=_period_end(obj),
                cancel_at_period_end=bool(obj.get("cancel_at_period_end")), **base)

        if etype == "invoice.payment_failed":
            parent = (obj.get("parent") or {}).get("subscription_details") or {}
            return BillingEvent(
                kind="PAST_DUE", external_customer_id=obj.get("customer") or "",
                external_subscription_id=parent.get("subscription") or obj.get("subscription") or "", **base)
        return None

    def manage_url(self, *, subscription, return_url) -> str:
        if not subscription.external_customer_id:
            raise GatewayError("No Stripe customer for this account.")
        try:
            session = self._client.v1.billing_portal.sessions.create(
                params={"customer": subscription.external_customer_id, "return_url": return_url})
        except stripe.StripeError as exc:
            raise GatewayError("Could not open the billing portal.") from exc
        return session.url
