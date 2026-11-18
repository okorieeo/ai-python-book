"""Reading Stripe objects into our own small, stable shapes."""
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class SubscriptionSnapshot:
    subscription_id: str
    customer_id: str
    status: str
    price_id: str
    plan_key: Optional[str]
    tier: str
    period_end: Optional[int]
    cancel_at_period_end: bool
    cancel_at: Optional[int]
    trial_end: Optional[int]
    canceled_at: Optional[int]
    user_id: Optional[str]          # from the subscription's metadata, set by us at checkout
    item_id: str = ""               # the subscription item to change on an upgrade
    multiple_items: bool = False


def subscription_snapshot(obj: dict, config) -> SubscriptionSnapshot:
    """Read a Stripe Subscription object (from an event or from the API).

    Since API version 2025-03-31 (basil) the billing period lives on each subscription ITEM, not on
    the subscription. We read the item first and fall back to the old top-level field, so objects
    from either shape work. Our model assumes one item per subscription; extra items are flagged.
    """
    items = (obj.get("items") or {}).get("data") or []
    if not items:
        raise ValueError("The subscription has no items.")
    item = items[0]
    price = item.get("price") or {}
    plan = config.plan_for_price(price.get("id", ""))
    period_end = item.get("current_period_end")
    if period_end is None:
        period_end = obj.get("current_period_end")
    customer = obj.get("customer")
    if isinstance(customer, dict):          # when the customer is expanded
        customer = customer.get("id")
    return SubscriptionSnapshot(
        subscription_id=obj["id"],
        customer_id=customer or "",
        status=obj["status"],
        price_id=price.get("id", ""),
        plan_key=plan.key if plan else None,
        tier=plan.tier if plan else "free",
        period_end=period_end,
        cancel_at_period_end=bool(obj.get("cancel_at_period_end")),
        cancel_at=obj.get("cancel_at"),
        trial_end=obj.get("trial_end"),
        canceled_at=obj.get("canceled_at"),
        user_id=(obj.get("metadata") or {}).get("user_id"),
        item_id=item.get("id", ""),
        multiple_items=len(items) > 1,
    )


def invoice_subscription_id(invoice: dict) -> Optional[str]:
    """The subscription an invoice belongs to. Newer API versions moved it under parent.subscription_details."""
    parent = invoice.get("parent") or {}
    details = parent.get("subscription_details") or {}
    return details.get("subscription") or invoice.get("subscription")
