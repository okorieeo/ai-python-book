"""A guided tour that prints real output for each tool in this chapter: python -m stripebilling.tour"""
import json

from .entitlements import DAY, decide_access
from .fixtures import START, make_event, payload_of
from .params import checkout_params, payment_intent_params, plan_change_params
from .simulate import SECRET, demo_config
from .store import SubscriptionRecord
from .webhooks import ManualVerifier, sign_payload

CONFIG = demo_config()


def title(text):
    print(f"\n== {text}")


def main():
    hosts = frozenset({"app.example.com"})
    args = dict(user_id="user-1", customer_id="cus_001", email="ada@example.com", allowed_hosts=hosts,
                success_url=CONFIG.success_url, cancel_url=CONFIG.cancel_url)

    title("1. Parameters for a subscription checkout with a free trial")
    print(json.dumps(checkout_params(plan=CONFIG.plan("pro_monthly"), trial_days=14, **args), indent=2))

    title("2. Parameters for a one-time purchase, and for embedded checkout")
    once = checkout_params(plan=CONFIG.plan("credits_100"), **args)
    print("one-time :", {k: once[k] for k in ("mode", "client_reference_id", "metadata")})
    emb = checkout_params(plan=CONFIG.plan("pro_monthly"), embedded=True, **args)
    print("embedded :", {k: emb[k] for k in ("ui_mode", "return_url")}, "| has cancel_url:", "cancel_url" in emb)
    print("payment_method_types sent:", "payment_method_types" in once)

    title("3. Upgrade and downgrade parameters")
    for direction in ("up", "down"):
        print(direction.ljust(5), plan_change_params(item_id="si_001", new_price_id="price_team_month", direction=direction))

    title("4. A signed webhook: the header, then four ways to fail")
    payload = payload_of(make_event("invoice.paid", {"id": "in_001"}, event_id="evt_demo"))
    header = sign_payload(payload, SECRET, START)
    print("Stripe-Signature:", header[:44] + "...")
    verifier = ManualVerifier(SECRET, clock=lambda: START + 10)
    print("valid            :", verifier.verify(payload, header)["id"])
    attempts = {"payload changed": (payload + b" ", header),
                "wrong secret": (payload, sign_payload(payload, "whsec_wrong_secret", START)),
                "one hour old": (payload, sign_payload(payload, SECRET, START - 3600)),
                "no header": (payload, "")}
    for label, (body, hdr) in attempts.items():
        try:
            verifier.verify(body, hdr)
            print(f"{label:<17}: ACCEPTED (bad!)")
        except Exception as error:
            print(f"{label:<17}: rejected - {error}")

    title("5. Who gets paid features? The same subscription at different moments")
    base = dict(user_id="u", customer_id="c", subscription_id="s", tier="pro", plan_key="pro_monthly",
                period_end=START + 30 * DAY)
    cases = [("active", {}, 5), ("trialing", {"trial_end": START + 14 * DAY}, 5),
             ("active, cancel at period end", {"cancel_at_period_end": True}, 20),
             ("past_due, day 1 of grace", {"past_due_since": START}, 1), ("past_due, day 4 (grace over)", {"past_due_since": START}, 4),
             ("canceled", {}, 5), ("unpaid", {}, 5), ("incomplete", {}, 5), ("paused", {}, 5)]
    for label, extra, day in cases:
        status = label.split(",")[0]
        decision = decide_access(SubscriptionRecord(status=status, **{**base, **extra}), START + day * DAY, 3)
        print(f"{label:<31} day {day:<2} -> {'PAID' if decision.paid else 'free':<4} {decision.reason}")


if __name__ == "__main__":
    main()
