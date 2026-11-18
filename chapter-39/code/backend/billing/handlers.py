"""
Example business handlers: the part that changes money and entitlements. Adapt names to Chapters 35 to 38.
They are written to be safe to run twice, and to never trust an amount that arrives in a webhook.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass
class Order:
    reference: str
    user_id: int
    amount_minor: int          # kobo or cents, fixed by US when the payment was initialised
    currency: str
    credits: int
    status: str = "pending"


@dataclass
class BillingState:
    """An in-memory stand-in for your billing tables."""
    credits: dict[int, int] = field(default_factory=dict)
    plans: dict[int, str] = field(default_factory=dict)
    plan_stamp: dict[int, int] = field(default_factory=dict)   # when (provider time) each plan was last set
    orders: dict[str, Order] = field(default_factory=dict)
    flagged: list[dict] = field(default_factory=list)       # things a human should look at

    def add_credits(self, user_id: int, n: int) -> None:
        self.credits[user_id] = self.credits.get(user_id, 0) + n

    def set_plan(self, user_id: int, plan: str, created: int) -> bool:
        """Providers do NOT promise delivery order. An older event must never overwrite a newer decision."""
        if created < self.plan_stamp.get(user_id, 0):
            return False
        self.plans[user_id], self.plan_stamp[user_id] = plan, created
        return True


def build_handlers(state: BillingState) -> dict[str, Callable[[dict], None]]:
    def stripe_checkout_completed(event: dict) -> None:
        obj = event["data"]["object"]
        state.add_credits(int(obj["client_reference_id"]), int(obj["metadata"]["credits"]))

    def stripe_invoice_paid(event: dict) -> None:
        meta = event["data"]["object"].get("metadata") or {}
        if "user_id" in meta and "plan" in meta:
            state.set_plan(int(meta["user_id"]), meta["plan"], int(event.get("created", 0)))

    def stripe_subscription_deleted(event: dict) -> None:
        meta = event["data"]["object"].get("metadata") or {}
        if "user_id" in meta:                               # an unknown customer is not an error: ignore it
            state.set_plan(int(meta["user_id"]), "free", int(event.get("created", 0)))

    def paystack_charge_success(event: dict) -> None:
        data = event["data"]
        order = state.orders.get(data.get("reference", ""))
        if order is None:
            state.flagged.append({"why": "unknown reference", "reference": data.get("reference")})
            return
        if order.status == "paid":                          # belt and braces: idempotent even without the store
            return
        # Never credit what the webhook CLAIMS was paid: compare with what WE asked for.
        if data.get("amount") != order.amount_minor or data.get("currency") != order.currency:
            state.flagged.append({"why": "amount or currency mismatch", "reference": order.reference,
                                  "expected": [order.amount_minor, order.currency],
                                  "got": [data.get("amount"), data.get("currency")]})
            return
        order.status = "paid"
        state.add_credits(order.user_id, order.credits)

    return {
        "checkout.session.completed": stripe_checkout_completed,
        "invoice.paid": stripe_invoice_paid,
        "customer.subscription.deleted": stripe_subscription_deleted,
        "charge.success": paystack_charge_success,
    }
