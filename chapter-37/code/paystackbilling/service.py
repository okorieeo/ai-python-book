"""The billing operations your views call: start a payment, verify it, manage the subscription."""
import time
from dataclasses import dataclass
from typing import Callable, Optional

from .entitlements import AccessDecision, DAY, decide_access
from .errors import AlreadySubscribed, ForbiddenReference, NoSubscription, UnknownPlan
from .handlers import apply_charge, place_snapshot, sync_subscription
from .params import initialize_params, subscription_params
from .snapshots import iso_time, subscription_snapshot
from .store import PendingTransaction
from .config import new_reference


@dataclass(frozen=True)
class User:
    id: str
    email: str
    name: str = ""


@dataclass
class PaymentStart:
    reference: str
    authorization_url: str
    access_code: str


class PaystackBillingService:
    def __init__(self, gateway, store, config, clock: Callable = time.time, notify: Callable = lambda *a, **k: None):
        self.gateway, self.store, self.config, self.clock, self.notify = gateway, store, config, clock, notify

    def access(self, user_id: str) -> AccessDecision:
        return decide_access(self.store.subscription_for(user_id), self.clock(), self.config.grace_days)

    # ---- starting a payment ----------------------------------------------------------------------
    def _start(self, user: User, plan, *, kind: str, amount: int, with_plan: bool) -> PaymentStart:
        reference = new_reference()
        params = initialize_params(
            email=user.email, amount=amount, currency=plan.currency, reference=reference,
            callback_url=self.config.callback_url, allowed_hosts=self.config.allowed_hosts, user_id=user.id,
            plan_key=plan.key, kind=kind, plan_code=plan.plan_code if with_plan else None)
        # Save what we expect BEFORE sending the customer away, so that whatever comes back can be compared.
        self.store.save_pending(PendingTransaction(reference, str(user.id), plan.key, kind, amount, plan.currency,
                                                   created_at=self.clock()))
        data = self.gateway.initialize_transaction(params)
        return PaymentStart(data["reference"], data["authorization_url"], data["access_code"])

    def start_payment(self, user: User, plan_key: str) -> PaymentStart:
        """A one-time purchase, such as a pack of credits."""
        plan = self.config.plan(plan_key)
        if plan.interval != "once":
            raise UnknownPlan(f"{plan_key} is a subscription plan, not a one-time purchase")
        return self._start(user, plan, kind="one_time", amount=plan.amount, with_plan=False)

    def start_subscription(self, user: User, plan_key: str) -> PaymentStart:
        plan = self.config.plan(plan_key)
        if plan.interval == "once":
            raise UnknownPlan(f"{plan_key} is a one-time purchase, not a subscription plan")
        record = self.store.subscription_for(user.id)
        if record and record.status in {"active", "attention", "non-renewing"} and self.access(user.id).paid:
            raise AlreadySubscribed("Manage the existing subscription instead of starting a second one.")
        if plan.trial_days and not self.store.has_used_trial(user.id):
            # A trial: charge a small amount ONLY to save a reusable card, then start the plan later.
            return self._start(user, plan, kind="trial_authorization", amount=self.config.trial_auth_amount, with_plan=False)
        return self._start(user, plan, kind="subscription", amount=plan.amount, with_plan=True)

    # ---- the callback page ---------------------------------------------------------------------
    def verify_payment(self, user: User, reference: str) -> dict:
        """Called when the customer returns from Paystack. Never trusts the URL: it asks Paystack."""
        pending = self.store.pending(reference)
        if pending is None or pending.user_id != str(user.id):
            raise ForbiddenReference("This payment does not belong to you.")
        if pending.status != "paid":
            data = self.gateway.verify_transaction(reference)
            status = data.get("status")
            if status == "success":
                apply_charge(store=self.store, config=self.config, gateway=self.gateway, data=data,
                             now=self.clock(), notify=self.notify)
            elif status in {"failed", "abandoned", "reversed"}:
                self.store.set_pending_status(reference, "failed" if status != "abandoned" else "abandoned")
        final = self.store.pending(reference).status
        decision = self.access(user.id)
        return {"status": final, "paid": decision.paid, "tier": decision.tier,
                "credits": self.store.credit_balance(user.id)}

    def reconcile_pending(self) -> dict:
        """Re-check payments that are still pending after a while. If both the callback and the webhook
        failed to reach us, this still finds the payment. Run it every few minutes."""
        now = self.clock()
        stale = self.store.list_pending(created_before=now - self.config.pending_check_after,
                                        created_after=now - self.config.pending_give_up_after)
        counts = {"checked": 0, "applied": 0}
        for pending in stale:
            counts["checked"] += 1
            data = self.gateway.verify_transaction(pending.reference)
            if data.get("status") == "success":
                if apply_charge(store=self.store, config=self.config, gateway=self.gateway, data=data,
                                now=now, notify=self.notify) == "applied":
                    counts["applied"] += 1
            elif data.get("status") in {"failed", "abandoned", "reversed"}:
                self.store.set_pending_status(pending.reference, "failed")
        return counts

    # ---- managing a subscription -----------------------------------------------------------------
    def _record(self, user: User):
        record = self.store.subscription_for(user.id)
        if record is None or record.status in {"cancelled", "completed"}:
            raise NoSubscription("There is no subscription to change.")
        return record

    def cancel(self, user: User) -> AccessDecision:
        """Stop auto-renewal. The customer keeps access until the next payment date (status non-renewing)."""
        record = self._record(user)
        self.gateway.disable_subscription(record.subscription_code, record.email_token)
        sync_subscription(self.store, self.config, self.gateway, record.subscription_code, self.clock(), user.id)
        return self.access(user.id)

    def resume(self, user: User) -> AccessDecision:
        record = self._record(user)
        self.gateway.enable_subscription(record.subscription_code, record.email_token)
        sync_subscription(self.store, self.config, self.gateway, record.subscription_code, self.clock(), user.id)
        return self.access(user.id)

    def card_update_link(self, user: User) -> str:
        """A Paystack-hosted page where the customer replaces the card on a subscription."""
        return self.gateway.manage_link(self._record(user).subscription_code)

    def change_plan(self, user: User, new_plan_key: str) -> AccessDecision:
        """Switch plans at the next payment date. Paystack has no proration and no in-place plan change,
        so we create the new subscription to start when the old one ends, and stop the old one renewing."""
        record = self._record(user)
        new_plan = self.config.plan(new_plan_key)
        old_plan = self.config.plan(record.plan_key) if record.plan_key else None
        if new_plan.interval == "once":
            raise UnknownPlan("A one-time purchase is not a subscription plan.")
        if old_plan and new_plan.currency != old_plan.currency:
            raise UnknownPlan("A subscription cannot switch currency. Cancel it and start a new one.")
        if new_plan.plan_code == (old_plan.plan_code if old_plan else None):
            return self.access(user.id)
        now = self.clock()
        start = record.next_payment_date if record.next_payment_date and record.next_payment_date > now else int(now) + DAY
        created = self.gateway.create_subscription(subscription_params(
            customer_code=record.customer_code, plan_code=new_plan.plan_code,
            authorization_code=record.authorization_code, start_date=iso_time(start)))
        self.gateway.disable_subscription(record.subscription_code, record.email_token)
        sync_subscription(self.store, self.config, self.gateway, record.subscription_code, now, user.id)
        current = self.store.subscription_for(user.id)
        current.pending_plan_key = new_plan_key
        current.pending_subscription_code = created["subscription_code"]
        self.store.save_subscription(current)
        return self.access(user.id)
