"""What we do for each Paystack event. Handlers are small, safe to run twice and trust the API over the event."""
from dataclasses import replace
from typing import Callable, Optional

from .entitlements import DAY
from .errors import UnresolvedCustomer
from .params import subscription_params
from .snapshots import SubscriptionSnapshot, iso_time, parse_time, subscription_snapshot
from .store import PaymentRecord, SubscriptionRecord


def place_snapshot(store, snap: SubscriptionSnapshot, user_id: str, now: float, trial_end: Optional[int] = None) -> str:
    """Save what Paystack says about a subscription as the user's record.

    A user normally has one subscription. During a scheduled plan switch there are two: the old one (now
    non-renewing) and the new one (waiting for its start date). The new one replaces the old only when the
    old one has ended, so a customer never loses the plan they already paid for. Returns what happened.
    """
    current = store.subscription_for(user_id)
    record = SubscriptionRecord(
        user_id=str(user_id), customer_code=snap.customer_code, subscription_code=snap.subscription_code,
        email_token=snap.email_token, status=snap.status, plan_key=snap.plan_key, tier=snap.tier,
        next_payment_date=snap.next_payment_date, authorization_code=snap.authorization_code,
        card_last4=snap.card_last4, trial_end=trial_end)
    if current is None or current.subscription_code == snap.subscription_code:
        if current is not None:
            record = replace(record, trial_end=trial_end if trial_end is not None else current.trial_end,
                             pending_plan_key=current.pending_plan_key,
                             pending_subscription_code=current.pending_subscription_code)
        store.save_subscription(record)
        return "updated" if current else "created"
    old_ended = (current.status in {"cancelled", "completed"} or
                 (current.next_payment_date is not None and now >= current.next_payment_date))
    if snap.subscription_code == current.pending_subscription_code and old_ended:
        store.save_subscription(record)                      # the scheduled switch has arrived
        return "switched"
    if current.status in {"cancelled", "completed"} and snap.status in {"active", "attention"}:
        store.save_subscription(record)                      # a fresh subscription after an old one ended
        return "replaced"
    return "ignored"


def sync_subscription(store, config, gateway, code: str, now: float, user_id: Optional[str] = None) -> Optional[str]:
    """Read the subscription from Paystack (the source of truth) and store it. Order of events no longer matters."""
    live = gateway.fetch_subscription(code)
    snap = subscription_snapshot(live, config)
    owner = user_id or store.user_id_for_customer(snap.customer_code)
    if owner is None:
        raise UnresolvedCustomer(f"No user for customer {snap.customer_code}")
    place_snapshot(store, snap, owner, now)
    return owner


def _find_subscription(gateway, customer_code: str, plan_code: str) -> Optional[dict]:
    customer = gateway.fetch_customer(customer_code)
    mine = [s for s in customer.get("subscriptions", [])
            if (s.get("plan") or {}).get("plan_code", s.get("plan")) == plan_code
            and s.get("status") in {"active", "attention", "non-renewing"}]
    return mine[0] if mine else None


def apply_charge(*, store, config, gateway, data: dict, now: float, notify: Callable) -> str:
    """Handle a successful charge. Used by the webhook AND by the callback page, so that either path
    grants the same thing exactly once. Returns a short word saying what happened."""
    if data.get("status") != "success":
        return "not_successful"
    reference = data.get("reference", "")
    pending = store.pending(reference)
    if pending is None:
        return _record_renewal(store, config, data)
    if pending.status == "paid":
        return "already_applied"
    currency = (data.get("currency") or "").upper()
    if data.get("amount") != pending.amount or currency != pending.currency:
        store.set_pending_status(reference, "mismatch")
        notify("amount_mismatch", pending.user_id, reference=reference, expected=pending.amount, got=data.get("amount"))
        return "mismatch"
    plan = config.plan(pending.plan_key)
    customer = data.get("customer") or {}
    if customer.get("customer_code"):
        store.link_customer(pending.user_id, customer["customer_code"])
    customer_code = store.customer_code_for(pending.user_id)
    store.save_payment(PaymentRecord(reference, pending.user_id, pending.kind, pending.amount, pending.currency, "paid"))

    if pending.kind == "one_time":
        store.grant_credits(pending.user_id, plan.credits, reference)
    elif pending.kind == "subscription":
        found = _find_subscription(gateway, customer_code, plan.plan_code)
        if found:                                           # otherwise the subscription.create event will sync it
            place_snapshot(store, subscription_snapshot(found, config), pending.user_id, now)
    elif pending.kind == "trial_authorization":
        auth = data.get("authorization") or {}
        if not auth.get("reusable") or not auth.get("authorization_code"):
            store.set_pending_status(reference, "failed")
            notify("card_not_reusable", pending.user_id, reference=reference)
            return "card_not_reusable"
        found = _find_subscription(gateway, customer_code, plan.plan_code)
        if found is None:
            start = int(now) + plan.trial_days * DAY
            found = gateway.create_subscription(subscription_params(
                customer_code=customer_code, plan_code=plan.plan_code,
                authorization_code=auth["authorization_code"], start_date=iso_time(start)))
        snap = subscription_snapshot(found, config)
        place_snapshot(store, snap, pending.user_id, now, trial_end=snap.next_payment_date)
        store.mark_trial_used(pending.user_id)
    store.set_pending_status(reference, "paid")
    return "applied"


def _record_renewal(store, config, data: dict) -> str:
    """A charge we did not start: Paystack charging a subscription on its schedule. Record it, nothing more.
    The subscription's own state is read from the API when the invoice events arrive."""
    plan = data.get("plan") or {}
    customer = (data.get("customer") or {}).get("customer_code", "")
    user_id = store.user_id_for_customer(customer)
    if not plan.get("plan_code") or user_id is None:
        return "ignored_not_ours"
    store.save_payment(PaymentRecord(data["reference"], user_id, "subscription_charge", data.get("amount", 0),
                                     (data.get("currency") or "").upper(), "paid"))
    return "renewal_recorded"


class PaystackHandlers:
    """Connects event names to methods. notify(kind, user_id, **details) sends emails or push messages."""

    def __init__(self, store, config, gateway, notify: Callable = lambda *a, **k: None, clock: Callable = None):
        import time
        self.store, self.config, self.gateway, self.notify = store, config, gateway, notify
        self.clock = clock or time.time

    def table(self) -> dict:
        sub = self.on_subscription_event
        return {
            "charge.success": self.on_charge_success,
            "subscription.create": sub,
            "subscription.not_renew": sub,
            "subscription.disable": sub,
            "invoice.create": sub,
            "invoice.update": sub,
            "invoice.payment_failed": sub,
            "subscription.expiring_cards": self.on_expiring_cards,
            "refund.processed": self.on_refund,
            "charge.dispute.create": self.on_dispute,
        }

    def on_charge_success(self, event: dict) -> None:
        apply_charge(store=self.store, config=self.config, gateway=self.gateway, data=event["data"],
                     now=self.clock(), notify=self.notify)

    def on_subscription_event(self, event: dict) -> None:
        name, data = event["event"], event["data"]
        code = data.get("subscription_code") or (data.get("subscription") or {}).get("subscription_code")
        if not code:
            raise ValueError(f"{name} has no subscription code")
        before = None
        user_id = self.store.user_id_for_customer((data.get("customer") or {}).get("customer_code", ""))
        if user_id:
            before = self.store.subscription_for(user_id)
        owner = sync_subscription(self.store, self.config, self.gateway, code, self.clock())
        after = self.store.subscription_for(owner)

        if name == "invoice.update" and data.get("paid"):
            ref = (data.get("transaction") or {}).get("reference") or data.get("invoice_code")
            self.store.save_payment(PaymentRecord(ref, owner, "subscription_charge", data.get("amount", 0),
                                                  ((data.get("transaction") or {}).get("currency") or "NGN").upper(), "paid"))
        if name == "invoice.create":
            self.notify("renewal_upcoming", owner, amount=data.get("amount"),
                        date=after.next_payment_date if after else None)
        elif name == "invoice.payment_failed" or (name == "invoice.update" and not data.get("paid")):
            self.notify("payment_failed", owner, subscription_code=code)
        elif name == "subscription.not_renew":
            self.notify("cancellation_scheduled", owner, until=after.next_payment_date if after else None)
        elif name == "subscription.disable" and not (before and before.status in {"cancelled", "completed"}):
            self.notify("subscription_ended", owner)

    def on_expiring_cards(self, event: dict) -> None:
        for item in event["data"] if isinstance(event["data"], list) else []:
            customer = (item.get("customer") or {}).get("customer_code", "")
            user_id = self.store.user_id_for_customer(customer)
            if user_id:
                self.notify("card_expiring", user_id, expires=item.get("expiry_date"))

    def on_refund(self, event: dict) -> None:
        data = event["data"]
        ref = data.get("transaction_reference") or (data.get("transaction") or {}).get("reference") or ""
        payment = self.store.payment(ref)
        if payment and data.get("amount", 0) >= payment.amount:      # only a full refund reverses credits
            self.store.save_payment(replace(payment, status="refunded"))
            self.store.reverse_credits(ref)

    def on_dispute(self, event: dict) -> None:
        self.notify("dispute_opened", None, reference=(event["data"].get("transaction") or {}).get("reference"))
