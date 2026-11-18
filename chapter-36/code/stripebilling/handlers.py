"""What we do for each Stripe event. Handlers are small, safe to run twice and tolerate odd ordering."""
from dataclasses import replace
from typing import Callable, Optional

from .errors import UnresolvedCustomer
from .snapshots import SubscriptionSnapshot, invoice_subscription_id, subscription_snapshot
from .store import PaymentRecord, SubscriptionRecord


def apply_snapshot(store, snap: SubscriptionSnapshot, user_id: str, event_created: Optional[int]) -> bool:
    """Save a subscription snapshot unless it is older than what we already have.

    event_created is the time of the Stripe event, or None when the snapshot came from reading the API
    (which is always current, and must not move the "newest event" marker). Returns True if applied.
    """
    current = store.subscription_for(user_id)
    if event_created is not None and current and event_created < current.last_event_created:
        return False                                   # an old event arriving late: ignore it
    marker = event_created if event_created is not None else (current.last_event_created if current else 0)
    past_due_since = None
    if snap.status == "past_due":
        past_due_since = current.past_due_since if current and current.past_due_since else (event_created or marker)
    store.save_subscription(SubscriptionRecord(
        user_id=str(user_id), customer_id=snap.customer_id, subscription_id=snap.subscription_id,
        status=snap.status, plan_key=snap.plan_key, tier=snap.tier, price_id=snap.price_id,
        period_end=snap.period_end, cancel_at_period_end=snap.cancel_at_period_end, cancel_at=snap.cancel_at,
        trial_end=snap.trial_end, canceled_at=snap.canceled_at, past_due_since=past_due_since,
        last_event_created=max(marker, current.last_event_created if current else 0),
    ))
    if snap.trial_end is not None:
        store.mark_trial_used(user_id)
    return True


def fulfil_payment_session(store, config, session: dict) -> bool:
    """Give a one-time purchase to the user, once, whichever of webhook or success page gets here first."""
    if session.get("mode") != "payment" or session.get("payment_status") != "paid":
        return False
    user_id = session.get("client_reference_id")
    plan = config.plan((session.get("metadata") or {}).get("plan_key", ""))
    pi = session.get("payment_intent") or session["id"]
    store.save_payment(PaymentRecord(
        ref=pi, user_id=str(user_id), kind="one_time", amount=session.get("amount_total") or 0,
        currency=session.get("currency") or "", status="paid", fulfil_ref=session["id"]))
    return store.grant_credits(user_id, plan.credits, session["id"])


class StripeHandlers:
    """Connects event types to methods. notify(kind, user_id, **details) sends emails or push messages."""

    def __init__(self, store, config, notify: Callable = lambda *a, **k: None):
        self.store, self.config, self.notify = store, config, notify

    def table(self) -> dict:
        sub = self.on_subscription
        return {
            "checkout.session.completed": self.on_checkout_completed,
            "checkout.session.async_payment_succeeded": self.on_checkout_completed,
            "checkout.session.async_payment_failed": self.on_async_payment_failed,
            "customer.subscription.created": sub,
            "customer.subscription.updated": sub,
            "customer.subscription.deleted": sub,
            "customer.subscription.paused": sub,
            "customer.subscription.resumed": sub,
            "customer.subscription.trial_will_end": self.on_trial_will_end,
            "invoice.paid": self.on_invoice_paid,
            "invoice.payment_failed": self.on_invoice_payment_failed,
            "payment_intent.succeeded": self.on_payment_intent_succeeded,
            "charge.refunded": self.on_charge_refunded,
            "charge.dispute.created": self.on_dispute,
        }

    # ---- finding the user -----------------------------------------------------------------------
    def _user_for(self, customer_id: str, hint: Optional[str] = None) -> str:
        user_id = self.store.user_id_for_customer(customer_id)
        if user_id is None and hint:
            self.store.link_customer(hint, customer_id)       # the id we put in metadata at checkout
            user_id = self.store.user_id_for_customer(customer_id)
        if user_id is None:
            raise UnresolvedCustomer(f"No user for customer {customer_id}")
        return user_id

    # ---- handlers ----------------------------------------------------------------------------
    def on_checkout_completed(self, event: dict) -> None:
        session = event["data"]["object"]
        user_id = session.get("client_reference_id")
        if session.get("customer") and user_id:
            linked = self.store.link_customer(user_id, session["customer"])
            if linked != session["customer"]:
                raise ValueError(f"User {user_id} is already linked to a different customer")
        if session.get("mode") == "payment":
            fulfil_payment_session(self.store, self.config, session)
        # Subscription state arrives through customer.subscription.* events.

    def on_async_payment_failed(self, event: dict) -> None:
        session = event["data"]["object"]
        self.notify("payment_failed", session.get("client_reference_id"), reason="delayed payment method failed")

    def on_subscription(self, event: dict) -> None:
        snap = subscription_snapshot(event["data"]["object"], self.config)
        user_id = self._user_for(snap.customer_id, snap.user_id)
        previous = self.store.subscription_for(user_id)
        if not apply_snapshot(self.store, snap, user_id, event["created"]):
            return
        if snap.cancel_at_period_end and not (previous and previous.cancel_at_period_end):
            self.notify("cancellation_scheduled", user_id, period_end=snap.period_end)
        if snap.status == "canceled" and not (previous and previous.status == "canceled"):
            self.notify("subscription_ended", user_id)

    def on_trial_will_end(self, event: dict) -> None:
        sub = event["data"]["object"]
        snap = subscription_snapshot(sub, self.config)
        self.notify("trial_ending", self._user_for(snap.customer_id, snap.user_id), trial_end=snap.trial_end)

    def on_invoice_paid(self, event: dict) -> None:
        invoice = event["data"]["object"]
        user_id = self._user_for(invoice["customer"])
        self.store.save_payment(PaymentRecord(
            ref=invoice["id"], user_id=user_id, kind="subscription_invoice", amount=invoice.get("amount_paid", 0),
            currency=invoice.get("currency", ""), status="paid", receipt_url=invoice.get("hosted_invoice_url", "")))

    def on_invoice_payment_failed(self, event: dict) -> None:
        invoice = event["data"]["object"]
        user_id = self._user_for(invoice["customer"])
        self.notify("payment_failed", user_id, attempt=invoice.get("attempt_count"),
                    next_attempt=invoice.get("next_payment_attempt"), pay_url=invoice.get("hosted_invoice_url"))

    def on_payment_intent_succeeded(self, event: dict) -> None:
        """Records payments made with the mobile Payment Sheet. Checkout payments carry no user id on
        the PaymentIntent (they are recorded from checkout.session.completed), so they are skipped here."""
        intent = event["data"]["object"]
        user_id = (intent.get("metadata") or {}).get("user_id")
        if not user_id or self.store.payment(intent["id"]):
            return
        self.store.save_payment(PaymentRecord(
            ref=intent["id"], user_id=str(user_id), kind="one_time", amount=intent.get("amount_received", 0),
            currency=intent.get("currency", ""), status="paid"))

    def on_charge_refunded(self, event: dict) -> None:
        charge = event["data"]["object"]
        payment = self.store.payment(charge.get("payment_intent") or "")
        if payment and charge.get("refunded"):
            self.store.save_payment(replace(payment, status="refunded"))
            if payment.fulfil_ref:
                self.store.reverse_credits(payment.fulfil_ref)

    def on_dispute(self, event: dict) -> None:
        dispute = event["data"]["object"]
        self.notify("dispute_opened", None, charge=dispute.get("charge"), reason=dispute.get("reason"))
