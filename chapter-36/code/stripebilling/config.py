"""Server-side billing settings: the only place that maps plan keys to Stripe prices."""
from dataclasses import dataclass, field
from typing import Optional

from .errors import UnknownPlan

TIER_RANK = {"free": 0, "pro": 1, "team": 2}


@dataclass(frozen=True)
class Plan:
    key: str                 # our name for it, e.g. "pro_monthly"
    tier: str                # "pro" or "team"
    interval: str            # "month", "year" or "once" (a one-time purchase)
    price_id: str            # the Stripe Price id (price_...), different in test and live mode
    credits: int = 0         # for one-time credit packs
    trial: bool = True       # may this plan start with a free trial?


@dataclass(frozen=True)
class BillingConfig:
    plans: dict
    livemode: bool = False
    success_url: str = "https://app.example.com/billing/success?session_id={CHECKOUT_SESSION_ID}"
    cancel_url: str = "https://app.example.com/billing"
    return_url: str = "https://app.example.com/billing"
    allowed_hosts: frozenset = field(default_factory=lambda: frozenset({"app.example.com"}))
    trial_days: int = 14
    grace_days: int = 3                       # how long a past_due customer keeps access
    expected_api_version: str = "2026-09-30.endive"

    def plan(self, key: str) -> Plan:
        try:
            return self.plans[key]
        except KeyError:
            raise UnknownPlan(f"Unknown plan: {key!r}") from None

    def plan_for_price(self, price_id: str) -> Optional[Plan]:
        return next((p for p in self.plans.values() if p.price_id == price_id), None)
