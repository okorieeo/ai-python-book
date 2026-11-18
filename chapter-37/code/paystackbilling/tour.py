"""A guided tour that prints real output for each tool in this chapter: python -m paystackbilling.tour"""
import hashlib
import hmac
import json
from decimal import Decimal

from .entitlements import DAY, decide_access
from .errors import BadAmount, SignatureError
from .fixtures import START, body_of, charge_data, event
from .money import format_money, to_subunit
from .params import initialize_params
from .simulate import SECRET, demo_config
from .store import SubscriptionRecord
from .webhooks import PaystackVerifier, event_key, sign_body

CONFIG = demo_config()


def title(text):
    print(f"\n== {text}")


def main():
    title("1. Money: whole numbers of the smallest unit")
    for amount, currency in [("5000", "NGN"), (Decimal("49.99"), "USD"), ("0.01", "NGN"), ("1500.5", "GHS")]:
        print(f"{str(amount):>8} {currency} -> {to_subunit(amount, currency):>8} smallest units -> {format_money(to_subunit(amount, currency), currency)}")
    for bad, currency in [(49.99, "USD"), ("49.999", "USD"), ("abc", "NGN"), ("12", "EUR")]:
        try:
            to_subunit(bad, currency)
        except (BadAmount, ValueError) as error:
            print(f"{bad!r:>8} {currency} -> refused: {error}")

    title("2. The same plan table, one price list per currency")
    for currency in ("NGN", "USD"):
        names = [f"{p.key} {format_money(p.amount, p.currency)}" for p in CONFIG.plans_for_currency(currency)]
        print(f"{currency}: " + "; ".join(names))

    title("3. What we send to /transaction/initialize")
    base = dict(email="ada@example.com", currency="NGN", callback_url="https://app.example.com/billing/callback",
                allowed_hosts=frozenset({"app.example.com"}), user_id="user-1")
    pro = CONFIG.plan("pro_monthly_ngn")
    print("subscription (no trial):")
    print(json.dumps(initialize_params(amount=pro.amount, reference="ps_demo1", plan_key=pro.key, kind="subscription",
                                       plan_code=pro.plan_code, **base), indent=2))
    print("trial: save a card first (no plan code, small amount):")
    print(json.dumps(initialize_params(amount=5000, reference="ps_demo2", plan_key=pro.key, kind="trial_authorization", **base), indent=2))

    title("4. A webhook signature, and four ways to fail")
    body = body_of(event("charge.success", charge_data(reference="ps_demo3", amount=200000)))
    signature = sign_body(body, SECRET)
    print(f"x-paystack-signature: {signature[:32]}... ({len(signature)} hex characters = SHA-512)")
    verifier = PaystackVerifier(SECRET)
    print("valid               :", verifier.verify(body, signature)["event"])
    attempts = {"body changed": (body + b" ", signature), "wrong key": (body, sign_body(body, "sk_test_wrong_key")),
                "SHA-256 instead": (body, hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()), "no header": (body, "")}
    for label, (b, s) in attempts.items():
        try:
            verifier.verify(b, s)
            print(f"{label:<20}: ACCEPTED (bad!)")
        except SignatureError as error:
            print(f"{label:<20}: rejected - {error}")
    print("event key (hash of the bytes):", event_key(body)[:24] + "...")

    title("5. Who gets paid features? Dates, not statuses")
    base = dict(user_id="u", customer_code="c", subscription_code="s", email_token="t", tier="pro", plan_key="pro_monthly_ngn",
                next_payment_date=START + 30 * DAY)
    cases = [("active", {}, 10), ("active, trial running", {"trial_end": START + 14 * DAY}, 10), ("active, day 1 after due date", {}, 31),
             ("active, day 4 after due date", {}, 34), ("attention (last charge failed)", {}, 20),
             ("attention, day 4 after due date", {}, 34), ("non-renewing, before the date", {}, 20),
             ("non-renewing, after the date", {}, 31), ("cancelled", {}, 20), ("completed", {}, 20)]
    for label, extra, day in cases:
        status = label.split(",")[0].split(" (")[0]
        decision = decide_access(SubscriptionRecord(status=status, **{**base, **extra}), START + day * DAY, 3)
        print(f"{label:<34} day {day:<2} -> {'PAID' if decision.paid else 'free':<4} {decision.reason}")


if __name__ == "__main__":
    main()
