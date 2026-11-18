"""Reading Paystack objects into our own small, stable shapes."""
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional


def parse_time(value) -> Optional[int]:
    """Paystack sends ISO 8601 text such as '2026-12-20T00:00:00.000Z'. Return unix seconds, or None."""
    if not value:
        return None
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp())


def iso_time(unix_seconds: int) -> str:
    """The format Paystack expects for start_date: ISO 8601 with a timezone."""
    return datetime.fromtimestamp(unix_seconds, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


@dataclass(frozen=True)
class SubscriptionSnapshot:
    subscription_code: str
    email_token: str
    status: str
    customer_code: str
    customer_email: str
    plan_code: str
    plan_key: Optional[str]
    tier: str
    next_payment_date: Optional[int]
    authorization_code: str
    card_last4: str


def subscription_snapshot(obj: dict, config) -> SubscriptionSnapshot:
    """Read a subscription object as returned by GET /subscription/:code (the 'data' part)."""
    plan = obj.get("plan") or {}
    plan_code = plan.get("plan_code", "") if isinstance(plan, dict) else str(plan)
    ours = config.plan_for_code(plan_code)
    customer = obj.get("customer") or {}
    auth = obj.get("authorization") or {}
    return SubscriptionSnapshot(
        subscription_code=obj["subscription_code"],
        email_token=obj.get("email_token", ""),
        status=obj["status"],
        customer_code=customer.get("customer_code", "") if isinstance(customer, dict) else "",
        customer_email=customer.get("email", "") if isinstance(customer, dict) else "",
        plan_code=plan_code,
        plan_key=ours.key if ours else None,
        tier=ours.tier if ours else "free",
        next_payment_date=parse_time(obj.get("next_payment_date")),
        authorization_code=auth.get("authorization_code", ""),
        card_last4=auth.get("last4", ""),
    )
