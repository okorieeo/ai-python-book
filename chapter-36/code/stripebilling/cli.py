"""python -m stripebilling.cli <simulate|attacks|plans>"""
import argparse
import sys

from .fixtures import START, checkout_session_obj, make_event, subscription_obj
from .simulate import SECRET, Clock, build_world, deliver, demo_config, format_rows, run_simulation
from .webhooks import sign_payload


def attacks():
    """Show how the processor answers bad, repeated, stale and out-of-order deliveries."""
    clock, config, store, gateway, service, processor, sent = build_world()
    good = make_event("checkout.session.completed", checkout_session_obj(), created=START)
    sub_new = make_event("customer.subscription.updated", subscription_obj(status="active", period_end=START + 99), created=START + 50)
    sub_old = make_event("customer.subscription.updated", subscription_obj(status="past_due", period_end=START + 99), created=START + 10)
    from .fixtures import payload_of
    rows = []

    def show(label, result):
        rows.append(f"{label:<44} -> HTTP {result.status} {result.outcome}")

    show("correct signature", deliver(processor, clock, good))
    show("same event delivered again", deliver(processor, clock, good))
    show("wrong signing secret", deliver(processor, clock, make_event("invoice.paid", {}), secret="whsec_wrong"))
    payload = payload_of(make_event("customer.subscription.updated", subscription_obj(status="active")))
    show("payload changed after signing", processor.handle(payload.replace(b"active", b"cancel"),
                                                              sign_payload(payload, SECRET, int(clock()))))
    stale = make_event("invoice.paid", {})
    show("signature older than five minutes", processor.handle(payload_of(stale),
                                                                sign_payload(payload_of(stale), SECRET, int(clock()) - 3600)))
    show("event from live mode in test mode", deliver(processor, clock, make_event("invoice.paid", {}, livemode=True)))
    show("event type we do not handle", deliver(processor, clock, make_event("payout.paid", {})))
    show("newer subscription event", deliver(processor, clock, sub_new))
    show("older event arriving late", deliver(processor, clock, sub_old))
    record = store.subscription_for("user-1")
    rows.append(f"{'status kept after the late event':<44} -> {record.status}")
    print("\n".join(rows))


def main(argv=None):
    parser = argparse.ArgumentParser(prog="stripebilling.cli")
    parser.add_argument("command", choices=["simulate", "attacks", "plans"])
    args = parser.parse_args(argv)
    if args.command == "simulate":
        rows, sent = run_simulation()
        print(format_rows(rows))
        print("\nmessages sent to the user:", ", ".join(kind for kind, _ in sent))
    elif args.command == "attacks":
        attacks()
    else:
        for plan in demo_config().plans.values():
            print(f"{plan.key:<14} tier={plan.tier:<5} interval={plan.interval:<6} price={plan.price_id} credits={plan.credits}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
