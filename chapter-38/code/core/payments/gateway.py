"""The one interface the rest of the app talks to. Stripe and Paystack hide behind it."""
from __future__ import annotations

import enum
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime

from .money import Money


class EventType(enum.StrEnum):
    PAYMENT_SUCCEEDED = "payment_succeeded"
    PAYMENT_FAILED = "payment_failed"
    REFUND_UPDATED = "refund_updated"
    SUBSCRIPTION_CANCELED = "subscription_canceled"
    RENEWAL_FAILED = "renewal_failed"
    DISPUTE_OPENED = "dispute_opened"
    IGNORED = "ignored"


class GatewayRejected(Exception):
    """The gateway definitely did not create anything (bad request, unsupported currency). Safe to try another."""


class GatewayUncertain(Exception):
    """Timeout or 5xx: a session MAY exist. Never fail over to another gateway on this."""


class SignatureError(Exception):
    pass


@dataclass(frozen=True)
class CheckoutRequest:
    reference: str            # OUR id; sent to the gateway so webhooks can find the payment
    amount: Money
    email: str
    success_url: str
    cancel_url: str
    idempotency_key: str
    description: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class CheckoutResult:
    provider: str
    provider_ref: str         # Stripe session/intent id, Paystack access_code
    redirect_url: str


@dataclass(frozen=True)
class NormalizedEvent:
    provider: str
    event_id: str             # unique per delivery source; used for deduplication
    type: EventType
    reference: str            # our payment reference (may be "" if the gateway did not echo it)
    provider_ref: str = ""
    amount_minor: int | None = None
    currency: str | None = None
    refund_ref: str = ""
    amount_is_cumulative: bool = False
    occurred_at: datetime | None = None
    raw_type: str = ""


@dataclass(frozen=True)
class VerifiedPayment:
    reference: str
    status: str               # "succeeded" | "failed" | "pending"
    amount: Money
    provider_ref: str


@dataclass(frozen=True)
class RefundResult:
    provider_ref: str
    status: str               # "pending" | "succeeded" | "failed"
    amount: Money


class PaymentGateway(ABC):
    code: str = ""
    currencies: frozenset[str] = frozenset()

    @abstractmethod
    def create_checkout(self, request: CheckoutRequest) -> CheckoutResult: ...

    @abstractmethod
    def verify(self, reference: str, provider_ref: str = "") -> VerifiedPayment:
        """Ask the gateway directly. Never trust a redirect or a webhook body alone for the amount."""

    @abstractmethod
    def refund(self, *, reference: str, provider_ref: str, amount: Money, idempotency_key: str) -> RefundResult: ...

    def list_transactions(self, start: datetime, end: datetime) -> list:
        """Settled transactions in a period, as reconciliation.Line objects. Optional; used by the daily job."""
        raise NotImplementedError

    @abstractmethod
    def verify_webhook(self, raw_body: bytes, headers: dict[str, str], *, now: int) -> None:
        """Raise SignatureError unless the request is authentic."""

    @abstractmethod
    def parse_webhook(self, raw_body: bytes) -> NormalizedEvent: ...
