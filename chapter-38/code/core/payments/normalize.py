"""Translate each gateway's webhook payload into our NormalizedEvent."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from .gateway import EventType, NormalizedEvent

_STRIPE = {
    "payment_intent.succeeded": EventType.PAYMENT_SUCCEEDED,
    "checkout.session.completed": EventType.PAYMENT_SUCCEEDED,
    "payment_intent.payment_failed": EventType.PAYMENT_FAILED,
    "charge.refunded": EventType.REFUND_UPDATED,
    "customer.subscription.deleted": EventType.SUBSCRIPTION_CANCELED,
    "invoice.payment_failed": EventType.RENEWAL_FAILED,
    "charge.dispute.created": EventType.DISPUTE_OPENED,
}
_PAYSTACK = {
    "charge.success": EventType.PAYMENT_SUCCEEDED,
    "refund.processed": EventType.REFUND_UPDATED,
    "subscription.disable": EventType.SUBSCRIPTION_CANCELED,
    "subscription.not_renew": EventType.SUBSCRIPTION_CANCELED,
    "invoice.payment_failed": EventType.RENEWAL_FAILED,
}


def parse_stripe(raw: bytes) -> NormalizedEvent:
    event = json.loads(raw)
    raw_type = event.get("type", "")
    obj = (event.get("data") or {}).get("object") or {}
    etype = _STRIPE.get(raw_type, EventType.IGNORED)
    metadata = obj.get("metadata") or {}
    reference = metadata.get("payment_reference") or obj.get("client_reference_id") or ""
    amount, cumulative = obj.get("amount"), False
    if etype == EventType.REFUND_UPDATED:
        amount, cumulative = obj.get("amount_refunded"), True    # Stripe reports the running total
    elif raw_type == "checkout.session.completed":
        amount = obj.get("amount_total")
    created = event.get("created")
    return NormalizedEvent(
        provider="stripe", event_id=event.get("id", ""), type=etype, reference=reference,
        provider_ref=obj.get("payment_intent") or obj.get("id", ""), amount_minor=amount,
        currency=(obj.get("currency") or "").upper() or None, amount_is_cumulative=cumulative,
        occurred_at=datetime.fromtimestamp(created, tz=timezone.utc) if created else None, raw_type=raw_type)


def parse_paystack(raw: bytes) -> NormalizedEvent:
    event = json.loads(raw)
    raw_type = event.get("event", "")
    data = event.get("data") or {}
    etype = _PAYSTACK.get(raw_type, EventType.IGNORED)
    if etype == EventType.PAYMENT_SUCCEEDED and data.get("status") != "success":
        etype = EventType.IGNORED
    if etype == EventType.REFUND_UPDATED:
        reference, refund_ref = data.get("transaction_reference", ""), data.get("refund_reference", "") or str(data.get("id", ""))
    else:
        reference, refund_ref = data.get("reference", ""), ""
    # Paystack has no event id: build a stable one from the event name and the object's identity.
    identity = data.get("id") or data.get("refund_reference") or data.get("subscription_code") or reference
    return NormalizedEvent(
        provider="paystack", event_id=f"{raw_type}:{identity}", type=etype, reference=reference,
        provider_ref=str(data.get("id", "")), amount_minor=data.get("amount"),
        currency=(data.get("currency") or "").upper() or None, refund_ref=refund_ref, raw_type=raw_type)
