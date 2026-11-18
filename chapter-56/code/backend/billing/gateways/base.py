"""The contract every payment gateway implements (the full version is built in Chapter 38)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

Kind = Literal["ACTIVE", "PAST_DUE", "CANCELED"]


class InvalidSignature(Exception):
    """The webhook was not signed by the gateway. Answer 400 and do nothing else."""


class GatewayError(Exception):
    """A call to the gateway's API failed."""


@dataclass(frozen=True)
class CheckoutSession:
    url: str
    reference: str = ""


@dataclass(frozen=True)
class BillingEvent:
    """What our app needs to know, whichever gateway said it."""

    provider: str
    event_id: str  # unique per provider: the idempotency key
    kind: Kind
    user_public_id: str | None = None
    customer_email: str | None = None
    plan_code: str | None = None
    price_ref: str | None = None  # Stripe price id or Paystack plan code, used to find the plan
    external_customer_id: str = ""
    external_subscription_id: str = ""
    period_end: datetime | None = None
    cancel_at_period_end: bool = False
    occurred_at: datetime | None = None
    amount_minor: int | None = None
    currency: str | None = None
    event_type: str = ""


class PaymentGateway(Protocol):
    code: str

    def create_checkout(self, *, user, plan, success_url: str, cancel_url: str) -> CheckoutSession: ...

    def parse_webhook(self, *, body: bytes, headers: dict[str, str]) -> BillingEvent | None:
        """Verify the signature FIRST, then translate. Return None for events we do not care about."""

    def manage_url(self, *, subscription, return_url: str) -> str: ...
