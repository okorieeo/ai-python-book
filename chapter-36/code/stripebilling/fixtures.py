"""Builders for Stripe-shaped objects and events, used by tests, the simulator and the docs.

The shapes follow Stripe's documented objects (trimmed to the fields our code reads), including
the billing period on subscription ITEMS and the invoice's subscription under parent.
"""
import json
import itertools

_counter = itertools.count(1)
START = 1_800_000_000          # an arbitrary fixed "now" so every example is repeatable
DAY = 86400


def subscription_obj(*, id="sub_001", customer="cus_001", status="active", price_id="price_pro_month",
                     period_end=START + 30 * DAY, cancel_at_period_end=False, cancel_at=None, trial_end=None,
                     canceled_at=None, user_id="user-1", item_id="si_001", legacy_period=False):
    item = {"id": item_id, "price": {"id": price_id, "currency": "usd"}, "quantity": 1}
    sub = {
        "id": id, "object": "subscription", "customer": customer, "status": status,
        "items": {"object": "list", "data": [item]},
        "cancel_at_period_end": cancel_at_period_end, "cancel_at": cancel_at, "trial_end": trial_end,
        "canceled_at": canceled_at, "metadata": {"user_id": user_id} if user_id else {},
    }
    if legacy_period:
        sub["current_period_end"] = period_end      # the shape before API version 2025-03-31
    else:
        item["current_period_start"] = period_end - 30 * DAY
        item["current_period_end"] = period_end
    return sub


def checkout_session_obj(*, id="cs_test_001", mode="subscription", payment_status="paid", customer="cus_001",
                         user_id="user-1", plan_key="pro_monthly", subscription="sub_001",
                         payment_intent=None, amount_total=2000, currency="usd"):
    return {
        "id": id, "object": "checkout.session", "mode": mode, "payment_status": payment_status,
        "customer": customer, "client_reference_id": user_id, "metadata": {"user_id": user_id, "plan_key": plan_key},
        "subscription": subscription if mode == "subscription" else None,
        "payment_intent": payment_intent, "amount_total": amount_total, "currency": currency,
    }


def invoice_obj(*, id="in_001", customer="cus_001", subscription="sub_001", amount_paid=2000, currency="usd",
                attempt_count=1, next_payment_attempt=None):
    return {
        "id": id, "object": "invoice", "customer": customer, "amount_paid": amount_paid, "currency": currency,
        "number": "A1B2-0001", "hosted_invoice_url": f"https://invoice.stripe.com/i/{id}",
        "attempt_count": attempt_count, "next_payment_attempt": next_payment_attempt,
        "parent": {"type": "subscription_details", "subscription_details": {"subscription": subscription}},
    }


def charge_obj(*, id="ch_001", payment_intent="pi_001", amount_refunded=2000, amount=2000):
    return {"id": id, "object": "charge", "payment_intent": payment_intent, "amount": amount,
            "amount_refunded": amount_refunded, "refunded": amount_refunded >= amount}


def make_event(event_type: str, obj: dict, *, created: int = START, event_id: str = None, livemode: bool = False,
               api_version: str = "2026-09-30.endive") -> dict:
    return {"id": event_id or f"evt_{next(_counter):04d}", "object": "event", "type": event_type,
            "created": created, "livemode": livemode, "api_version": api_version,
            "data": {"object": obj}}


def payload_of(event: dict) -> bytes:
    """The raw bytes Stripe would send. Signatures are computed over exactly these bytes."""
    return json.dumps(event, separators=(",", ":")).encode("utf-8")
