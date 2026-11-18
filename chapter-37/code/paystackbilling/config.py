"""Server-side billing settings: the only place that maps plan keys to Paystack plans and amounts."""
import secrets
from dataclasses import dataclass, field
from typing import Optional

from .errors import UnknownPlan
from .money import check_currency

TIER_RANK = {"free": 0, "pro": 1, "team": 2}


@dataclass(frozen=True)
class Plan:
    key: str                  # our name, e.g. "pro_monthly_ngn"
    tier: str                 # "pro" or "team"
    interval: str             # "monthly", "annually" or "once"
    amount: int               # smallest units (kobo). We check every payment against this number
    currency: str
    plan_code: str = ""       # Paystack plan code (PLN_...). Empty for one-time purchases
    credits: int = 0          # for one-time credit packs
    trial_days: int = 0       # a free trial before the first charge (0 = none)

    def __post_init__(self):
        check_currency(self.currency)
        if self.interval != "once" and not self.plan_code:
            raise ValueError(f"{self.key}: a recurring plan needs a Paystack plan_code")
        if isinstance(self.amount, bool) or not isinstance(self.amount, int) or self.amount <= 0:
            raise ValueError(f"{self.key}: amount must be a positive whole number of the smallest unit")


@dataclass(frozen=True)
class PaystackConfig:
    plans: dict
    livemode: bool = False
    callback_url: str = "https://app.example.com/billing/callback"
    allowed_hosts: frozenset = field(default_factory=lambda: frozenset({"app.example.com"}))
    grace_days: int = 3
    trial_auth_amount: int = 5000           # kobo charged once to save a card for a trial (50 naira)
    pending_check_after: int = 900          # re-verify a payment still pending after 15 minutes
    pending_give_up_after: int = 72 * 3600  # and stop checking after 72 hours

    def plan(self, key: str) -> Plan:
        try:
            return self.plans[key]
        except KeyError:
            raise UnknownPlan(f"Unknown plan: {key!r}") from None

    def plan_for_code(self, plan_code: str) -> Optional[Plan]:
        return next((p for p in self.plans.values() if p.plan_code and p.plan_code == plan_code), None)

    def plans_for_currency(self, currency: str) -> list:
        """The price list for one currency. A Paystack plan has one fixed currency, so each currency
        needs its own plans. Never convert prices on the fly."""
        code = check_currency(currency)
        return [p for p in self.plans.values() if p.currency == code]


def new_reference(prefix: str = "ps") -> str:
    """A unique payment reference we make ourselves. Paystack rejects a duplicate reference, which is
    exactly what makes a retried initialize safe. Allowed characters are letters, digits, - . and =."""
    return f"{prefix}_{secrets.token_hex(12)}"
