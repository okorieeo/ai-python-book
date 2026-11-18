"""Billing records and an in-memory store with the same methods as the Django one."""
from dataclasses import dataclass, replace
from typing import Optional


@dataclass
class PendingTransaction:
    """A payment we started and have not finished. It remembers what we EXPECT, so that whatever
    Paystack later reports can be compared with it."""

    reference: str
    user_id: str
    plan_key: str
    kind: str                 # "one_time", "subscription", "trial_authorization" or "plan_switch"
    amount: int               # smallest units we expect to be paid
    currency: str
    status: str = "pending"   # pending, paid, mismatch, failed, abandoned
    created_at: float = 0.0
    access_code: str = ""


@dataclass
class SubscriptionRecord:
    user_id: str
    customer_code: str
    subscription_code: str
    email_token: str
    status: str                          # Paystack: active, non-renewing, attention, completed, cancelled
    plan_key: Optional[str] = None
    tier: str = "free"
    next_payment_date: Optional[int] = None   # unix seconds
    authorization_code: str = ""
    card_last4: str = ""
    trial_end: Optional[int] = None
    pending_plan_key: Optional[str] = None          # a plan switch scheduled for the next payment date
    pending_subscription_code: Optional[str] = None


@dataclass
class PaymentRecord:
    ref: str                  # the Paystack transaction reference or invoice code
    user_id: str
    kind: str                 # "one_time", "trial_authorization", "subscription_charge"
    amount: int
    currency: str
    status: str               # "paid" or "refunded"


class InMemoryBillingStore:
    """Plain dictionaries. Every method here exists on the Django store too."""

    def __init__(self):
        self._customers = {}      # user_id -> customer_code
        self._users = {}          # customer_code -> user_id
        self._pending = {}
        self._subs = {}           # user_id -> SubscriptionRecord
        self._payments = {}
        self._credits = {}
        self._grants = {}
        self._trial_used = set()
        self._events = {}

    # ---- customers ------------------------------------------------------------------------------
    def customer_code_for(self, user_id) -> Optional[str]:
        return self._customers.get(str(user_id))

    def user_id_for_customer(self, customer_code: str) -> Optional[str]:
        return self._users.get(customer_code)

    def link_customer(self, user_id, customer_code: str) -> str:
        """The first link wins. A second, different code for the same user is ignored."""
        user_id = str(user_id)
        if user_id not in self._customers:
            self._customers[user_id] = customer_code
            self._users[customer_code] = user_id
        return self._customers[user_id]

    # ---- pending transactions -------------------------------------------------------------------
    def save_pending(self, pending: PendingTransaction) -> None:
        self._pending[pending.reference] = replace(pending)

    def pending(self, reference: str) -> Optional[PendingTransaction]:
        found = self._pending.get(reference)
        return replace(found) if found else None

    def set_pending_status(self, reference: str, status: str) -> None:
        self._pending[reference].status = status

    def list_pending(self, *, created_before: float, created_after: float) -> list:
        return [replace(p) for p in self._pending.values()
                if p.status == "pending" and created_after <= p.created_at <= created_before]

    # ---- subscriptions --------------------------------------------------------------------------
    def subscription_for(self, user_id) -> Optional[SubscriptionRecord]:
        found = self._subs.get(str(user_id))
        return replace(found) if found else None

    def save_subscription(self, record: SubscriptionRecord) -> None:
        self._subs[str(record.user_id)] = replace(record)

    def has_used_trial(self, user_id) -> bool:
        return str(user_id) in self._trial_used

    def mark_trial_used(self, user_id) -> None:
        self._trial_used.add(str(user_id))

    # ---- payments and credits -------------------------------------------------------------------
    def payment(self, ref: str) -> Optional[PaymentRecord]:
        return self._payments.get(ref)

    def save_payment(self, record: PaymentRecord) -> None:
        self._payments[record.ref] = record

    def grant_credits(self, user_id, amount: int, ref: str) -> bool:
        if ref in self._grants:
            return False
        self._grants[ref] = [str(user_id), amount, False]
        self._credits[str(user_id)] = self._credits.get(str(user_id), 0) + amount
        return True

    def reverse_credits(self, ref: str) -> bool:
        grant = self._grants.get(ref)
        if not grant or grant[2]:
            return False
        grant[2] = True
        self._credits[grant[0]] -= grant[1]
        return True

    def credit_balance(self, user_id) -> int:
        return self._credits.get(str(user_id), 0)

    # ---- the webhook event log ------------------------------------------------------------------
    def begin_event(self, event_key: str, event_type: str, now: float, lease_seconds: int = 300) -> str:
        """Claim an event. Returns "run", "duplicate" or "busy". See the Stripe chapter for the idea."""
        entry = self._events.get(event_key)
        if entry:
            if entry["status"] in {"processed", "ignored"}:
                return "duplicate"
            if entry["status"] == "processing" and now - entry["started"] < lease_seconds:
                return "busy"
            entry.update(status="processing", started=now, attempts=entry["attempts"] + 1)
            return "run"
        self._events[event_key] = {"status": "processing", "type": event_type, "attempts": 1, "started": now, "error": ""}
        return "run"

    def finish_event(self, event_key: str, status: str, error: str = "") -> None:
        self._events[event_key].update(status=status, error=error[:300])

    def event(self, event_key: str) -> Optional[dict]:
        entry = self._events.get(event_key)
        return dict(entry) if entry else None
