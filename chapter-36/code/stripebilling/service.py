"""The billing operations your views call: start checkout, open the portal, change or cancel a plan."""
import time
from dataclasses import dataclass
from typing import Callable, Optional

from .config import TIER_RANK
from .entitlements import AccessDecision, decide_access
from .errors import AlreadySubscribed, ForbiddenSession, NoCustomer, NoSubscription
from .handlers import apply_snapshot, fulfil_payment_session
from .params import cancel_params, checkout_params, idempotency_key, plan_change_params, portal_params
from .snapshots import subscription_snapshot


@dataclass(frozen=True)
class User:
    id: str
    email: str
    name: str = ""


@dataclass
class CheckoutStart:
    session_id: str
    url: Optional[str]              # hosted checkout: redirect the browser here
    client_secret: Optional[str]    # embedded checkout: give this to Stripe.js


class BillingService:
    def __init__(self, gateway, store, config, clock: Callable = time.time):
        self.gateway, self.store, self.config, self.clock = gateway, store, config, clock

    # ---- customers ---------------------------------------------------------------------------
    def customer_id(self, user: User) -> str:
        """The user's Stripe customer, created on first use. The idempotency key prevents a double
        click from creating two customers."""
        existing = self.store.customer_id_for(user.id)
        if existing:
            return existing
        created = self.gateway.create_customer(
            email=user.email, name=user.name, metadata={"user_id": str(user.id)},
            idempotency_key=idempotency_key("customer", user.id))
        return self.store.link_customer(user.id, created["id"])

    # ---- reading state -------------------------------------------------------------------------
    def access(self, user_id: str) -> AccessDecision:
        return decide_access(self.store.subscription_for(user_id), self.clock(), self.config.grace_days)

    # ---- checkout ------------------------------------------------------------------------------
    def start_checkout(self, user: User, plan_key: str, *, embedded: bool = False) -> CheckoutStart:
        plan = self.config.plan(plan_key)                       # raises UnknownPlan for anything not ours
        trial_days = None
        if plan.interval != "once":
            record = self.store.subscription_for(user.id)
            if record and record.status in {"active", "trialing", "past_due", "incomplete", "paused"}:
                raise AlreadySubscribed("Use the billing portal or change plan instead of a second checkout.")
            if plan.trial and not self.store.has_used_trial(user.id):
                trial_days = self.config.trial_days
        params = checkout_params(
            plan=plan, user_id=user.id, customer_id=self.customer_id(user), email=user.email,
            success_url=self.config.success_url, cancel_url=self.config.cancel_url,
            allowed_hosts=self.config.allowed_hosts, trial_days=trial_days, embedded=embedded)
        bucket = int(self.clock() // 300)                       # one session per five minutes per request
        session = self.gateway.create_checkout_session(
            params, idempotency_key("checkout", user.id, plan_key, trial_days, embedded, bucket))
        return CheckoutStart(session["id"], session.get("url"), session.get("client_secret"))

    def sync_checkout(self, user: User, session_id: str) -> dict:
        """Called by the success page. Reads the session from Stripe (never trusts the browser) and applies it.

        Works even if the webhook has not arrived yet, and is safe if it arrives later: both paths write
        the same state and fulfil one-time purchases only once.
        """
        session = self.gateway.retrieve_checkout_session(session_id)
        if str(session.get("client_reference_id")) != str(user.id):
            raise ForbiddenSession("This checkout session does not belong to you.")
        if session.get("customer"):
            self.store.link_customer(user.id, session["customer"])
        fulfilled = False
        if session["mode"] == "subscription" and isinstance(session.get("subscription"), dict):
            snap = subscription_snapshot(session["subscription"], self.config)
            apply_snapshot(self.store, snap, user.id, None)
        elif session["mode"] == "payment":
            fulfilled = fulfil_payment_session(self.store, self.config, session)
        decision = self.access(user.id)
        return {"paid": decision.paid, "tier": decision.tier, "credits": self.store.credit_balance(user.id),
                "fulfilled_now": fulfilled}

    # ---- the customer portal -------------------------------------------------------------------
    def open_portal(self, user: User) -> str:
        customer = self.store.customer_id_for(user.id)
        if not customer:
            raise NoCustomer("Start a checkout first.")
        return self.gateway.create_portal_session(
            portal_params(customer, self.config.return_url, self.config.allowed_hosts))["url"]

    # ---- changing and cancelling -----------------------------------------------------------------
    def _active_record(self, user: User):
        record = self.store.subscription_for(user.id)
        if record is None or record.status in {"canceled", "incomplete_expired"}:
            raise NoSubscription("There is no subscription to change.")
        return record

    def change_plan(self, user: User, new_plan_key: str) -> AccessDecision:
        record = self._active_record(user)
        new_plan = self.config.plan(new_plan_key)
        if new_plan.interval == "once":
            raise NoSubscription("A one-time purchase is not a subscription plan.")
        live = self.gateway.retrieve_subscription(record.subscription_id)
        snap = subscription_snapshot(live, self.config)
        if snap.price_id == new_plan.price_id:
            return self.access(user.id)
        direction = ("up" if TIER_RANK[new_plan.tier] > TIER_RANK[record.tier] else
                     "down" if TIER_RANK[new_plan.tier] < TIER_RANK[record.tier] else "same")
        params = plan_change_params(item_id=snap.item_id, new_price_id=new_plan.price_id, direction=direction)
        updated = self.gateway.update_subscription(
            record.subscription_id, params, idempotency_key("change", user.id, record.subscription_id, new_plan_key,
                                                           int(self.clock() // 300)))
        apply_snapshot(self.store, subscription_snapshot(updated, self.config), user.id, None)
        return self.access(user.id)

    def cancel(self, user: User, *, immediately: bool = False) -> AccessDecision:
        record = self._active_record(user)
        if immediately:
            updated = self.gateway.cancel_subscription(record.subscription_id)
        else:
            updated = self.gateway.update_subscription(
                record.subscription_id, cancel_params(True), idempotency_key("cancel", user.id, record.subscription_id))
        apply_snapshot(self.store, subscription_snapshot(updated, self.config), user.id, None)
        return self.access(user.id)

    def resume(self, user: User) -> AccessDecision:
        record = self._active_record(user)
        updated = self.gateway.update_subscription(
            record.subscription_id, cancel_params(False),
            idempotency_key("resume", user.id, record.subscription_id, int(self.clock() // 300)))
        apply_snapshot(self.store, subscription_snapshot(updated, self.config), user.id, None)
        return self.access(user.id)

    def reconcile(self, user: User) -> AccessDecision:
        """Repair drift: read the subscription from Stripe and overwrite our copy. Run it nightly or on demand."""
        record = self.store.subscription_for(user.id)
        if record:
            live = self.gateway.retrieve_subscription(record.subscription_id)
            apply_snapshot(self.store, subscription_snapshot(live, self.config), user.id, None)
        return self.access(user.id)
