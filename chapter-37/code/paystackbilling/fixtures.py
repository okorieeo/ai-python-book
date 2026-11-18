"""Builders for Paystack-shaped objects and webhook events, used by tests, the simulator and the docs.

The shapes follow Paystack's documented payloads, trimmed to the fields our code reads.
"""
import itertools
import json

_ids = itertools.count(1000)
START = 1_800_000_000            # a fixed "now" so every example is repeatable
DAY = 86400


def iso(unix_seconds: int) -> str:
    from .snapshots import iso_time
    return iso_time(unix_seconds).replace("+00:00", ".000Z")


def customer_obj(code="CUS_001", email="ada@example.com"):
    return {"id": 24259516, "customer_code": code, "email": email, "first_name": "Ada", "last_name": "Obi"}


def authorization_obj(code="AUTH_001", reusable=True, last4="4081"):
    return {"authorization_code": code, "bin": "408408", "last4": last4, "exp_month": "12", "exp_year": "2030",
            "channel": "card", "card_type": "visa", "bank": "Test Bank", "country_code": "NG", "brand": "visa",
            "reusable": reusable}


def subscription_obj(*, code="SUB_001", token="tok_001", status="active", plan_code="PLN_pro_m", customer="CUS_001",
                     next_payment=START + 30 * DAY, auth="AUTH_001", amount=500000):
    return {
        "subscription_code": code, "email_token": token, "status": status, "amount": amount,
        "next_payment_date": iso(next_payment) if next_payment else None,
        "plan": {"plan_code": plan_code, "name": plan_code, "amount": amount, "interval": "monthly", "currency": "NGN"},
        "customer": customer_obj(customer), "authorization": authorization_obj(auth),
    }


def charge_data(*, reference, amount, currency="NGN", user_id="user-1", plan_key="credits_100", kind="one_time",
                customer="CUS_001", status="success", reusable=True, auth="AUTH_001", plan=None):
    return {
        "id": next(_ids), "domain": "test", "status": status, "reference": reference, "amount": amount,
        "currency": currency, "gateway_response": "Successful", "channel": "card",
        "metadata": {"user_id": user_id, "plan_key": plan_key, "kind": kind},
        "customer": customer_obj(customer), "authorization": authorization_obj(auth, reusable),
        "plan": plan or {},
    }


def event(name: str, data) -> dict:
    """Paystack events have only two top-level fields: the name and the data. There is no event id."""
    return {"event": name, "data": data}


def body_of(evt: dict) -> bytes:
    """The raw bytes Paystack would POST. The signature is computed over exactly these bytes."""
    return json.dumps(evt, separators=(",", ":")).encode("utf-8")


def invoice_data(sub: dict, *, paid: bool, reference="inv_ref_001", invoice_code="INV_001", amount=500000):
    return {"domain": "test", "invoice_code": invoice_code, "amount": amount, "status": "success" if paid else "failed",
            "paid": paid, "subscription": {k: sub[k] for k in ("subscription_code", "email_token", "status", "next_payment_date")},
            "customer": sub["customer"], "transaction": {"reference": reference, "status": "success" if paid else "failed",
                                                          "amount": amount, "currency": "NGN"}}
