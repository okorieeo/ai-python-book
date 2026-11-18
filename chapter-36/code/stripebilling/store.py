"""Billing records and an in-memory store with the same methods as the Django one."""
from dataclasses import dataclass, field, replace
from typing import Optional


@dataclass
class SubscriptionRecord:
    """What we know about one user's subscription. Stripe is the source of truth; this is a copy."""

    user_id: str
    customer_id: str
    subscription_id: str
    status: str                          # Stripe's status: active, trialing, past_due, canceled, ...
    plan_key: Optional[str] = None
    tier: str = "free"
    price_id: str = ""
    period_end: Optional[int] = None     # unix seconds
    cancel_at_period_end: bool = False
    cancel_at: Optional[int] = None
    trial_end: Optional[int] = None
    canceled_at: Optional[int] = None
    past_due_since: Optional[int] = None
    last_event_created: int = 0          # newest Stripe event applied; older events are ignored


@dataclass
class PaymentRecord:
    ref: str                  # a PaymentIntent id or an invoice id
    user_id: str
    kind: str                 # "one_time" or "subscription_invoice"
    amount: int               # in the smallest currency unit (cents, kobo)
    currency: str
    status: str               # "paid" or "refunded"
    fulfil_ref: str = ""      # the checkout session that granted credits, if any
    receipt_url: str = ""


class InMemoryBillingStore:
    """Plain dictionaries. Every method here exists on the Django store too."""

    def __init__(self):
        self._customers = {}        # user_id -> customer_id
        self._users = {}            # customer_id -> user_id
        self._subs = {}             # user_id -> SubscriptionRecord
        self._payments = {}         # ref -> PaymentRecord
        self._credits = {}          # user_id -> balance
        self._grants = {}           # ref -> (user_id, amount, reversed)
        self._trial_used = set()
        self._events = {}           # event_id -> dict(status, type, attempts, started, error)

    # ---- customers --------------------------------------------------------------------------
    def customer_id_for(self, user_id: str) -> Optional[str]:
        return self._customers.get(str(user_id))

    def user_id_for_customer(self, customer_id: str) -> Optional[str]:
        return self._users.get(customer_id)

    def link_customer(self, user_id: str, customer_id: str) -> str:
        """Connect a user to a Stripe customer. The first link wins; a second one is ignored."""
        user_id = str(user_id)
        if user_id not in self._customers:
            self._customers[user_id] = customer_id
            self._users[customer_id] = user_id
        return self._customers[user_id]

    # ---- subscriptions ----------------------------------------------------------------------
    def subscription_for(self, user_id: str) -> Optional[SubscriptionRecord]:
        record = self._subs.get(str(user_id))
        return replace(record) if record else None

    def save_subscription(self, record: SubscriptionRecord) -> None:
        self._subs[str(record.user_id)] = replace(record)

    def has_used_trial(self, user_id: str) -> bool:
        return str(user_id) in self._trial_used

    def mark_trial_used(self, user_id: str) -> None:
        self._trial_used.add(str(user_id))

    # ---- payments and credits -----------------------------------------------------------------
    def payment(self, ref: str) -> Optional[PaymentRecord]:
        return self._payments.get(ref)

    def save_payment(self, record: PaymentRecord) -> None:
        self._payments[record.ref] = record

    def grant_credits(self, user_id: str, amount: int, ref: str) -> bool:
        """Add credits once per ref. Returns False if this ref was already granted."""
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
        self._credits[grant[0]] = self._credits.get(grant[0], 0) - grant[1]
        return True

    def credit_balance(self, user_id: str) -> int:
        return self._credits.get(str(user_id), 0)

    # ---- the webhook event log ----------------------------------------------------------------
    def begin_event(self, event_id: str, event_type: str, now: float, lease_seconds: int = 300) -> str:
        """Claim an event for processing. Returns "run", "duplicate" or "busy".

        A processed or ignored event is a duplicate. An event another worker is processing right now
        is busy, unless its lease has run out (the worker probably died), which allows a retry.
        """
        entry = self._events.get(event_id)
        if entry:
            if entry["status"] in {"processed", "ignored"}:
                return "duplicate"
            if entry["status"] == "processing" and now - entry["started"] < lease_seconds:
                return "busy"
            entry.update(status="processing", started=now, attempts=entry["attempts"] + 1)
            return "run"
        self._events[event_id] = {"status": "processing", "type": event_type, "attempts": 1, "started": now, "error": ""}
        return "run"

    def finish_event(self, event_id: str, status: str, error: str = "") -> None:
        self._events[event_id].update(status=status, error=error[:300])

    def event(self, event_id: str) -> Optional[dict]:
        entry = self._events.get(event_id)
        return dict(entry) if entry else None
