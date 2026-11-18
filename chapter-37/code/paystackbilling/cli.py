"""python -m paystackbilling.cli <simulate|attacks|plans>"""
import argparse
import hashlib
import hmac
import sys

from .fixtures import body_of, charge_data, event
from .money import format_money
from .simulate import SECRET, build_world, deliver, demo_config, format_rows, run_simulation
from .service import User
from .webhooks import sign_body


def attacks():
    clock, config, store, gateway, service, processor, sent = build_world()
    user = User("user-1", "ada@example.com")
    start = service.start_payment(user, "credits_100")
    good = event("charge.success", gateway_pay(gateway, start.reference))
    rows = []

    def show(label, result):
        rows.append(f"{label:<46} -> HTTP {result.status} {result.outcome}")

    body = body_of(good)
    show("correct signature", processor.handle(body, sign_body(body, SECRET)))
    show("a captured valid request sent again", processor.handle(body, sign_body(body, SECRET)))
    show("signature made with SHA-256 instead of SHA-512", processor.handle(body, hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()))
    show("signature made with the wrong key", processor.handle(body, sign_body(body, "sk_test_wrong")))
    show("body changed after signing", processor.handle(body + b" ", sign_body(body, SECRET)))
    show("no signature header", processor.handle(body, ""))
    live = event("charge.success", dict(charge_data(reference="x", amount=1), domain="live"))
    show("live-mode event in test mode", deliver(processor, live))
    show("event type we do not handle", deliver(processor, event("transfer.success", {"domain": "test"})))
    rows.append(f"{'credits after all of that':<46} -> {store.credit_balance('user-1')}")

    start2 = service.start_payment(user, "credits_100")
    cheap = charge_data(reference=start2.reference, amount=5000, plan_key="credits_100")   # paid N50 for a N2,000 pack
    show("forged: amount lower than the price", deliver(processor, event("charge.success", cheap)))
    rows.append(f"{'credits after the underpaid charge':<46} -> {store.credit_balance('user-1')}")
    show("charge.success for a reference we never made", deliver(processor, event("charge.success", charge_data(reference="made_up", amount=200000))))
    print("\n".join(rows))
    print("alerts sent to the team:", [k for k, _ in sent])


def gateway_pay(gateway, reference):
    return gateway.pay(reference)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="paystackbilling.cli")
    parser.add_argument("command", choices=["simulate", "attacks", "plans"])
    args = parser.parse_args(argv)
    if args.command == "simulate":
        rows, sent = run_simulation()
        print(format_rows(rows))
        print("\nmessages sent to the user:", ", ".join(kind for kind, _ in sent))
    elif args.command == "attacks":
        attacks()
    else:
        for p in demo_config().plans.values():
            print(f"{p.key:<18} {p.tier:<5} {p.interval:<9} {format_money(p.amount, p.currency):>12} {p.currency} code={p.plan_code or '-'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
