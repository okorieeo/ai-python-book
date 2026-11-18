"""Start a payment: record it first, then ask a gateway, and fail over only when it is safe."""
from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime
from typing import Mapping, Protocol

from .gateway import (CheckoutRequest, CheckoutResult, GatewayRejected, GatewayUncertain, PaymentGateway)
from .money import Money
from .routing import GatewayRouter, NoGatewayError
from .states import PaymentStatus


class CheckoutFailed(Exception):
    def __init__(self, message: str, *, retry_same_key: bool):
        super().__init__(message)
        self.retry_same_key = retry_same_key


@dataclass
class PaymentRecord:
    reference: str
    idempotency_key: str
    user_id: str
    amount: Money
    status: PaymentStatus = PaymentStatus.PENDING
    provider: str = ""
    provider_ref: str = ""
    redirect_url: str = ""
    attempts: tuple[str, ...] = ()
    refunded_minor: int = 0
    paid_at: datetime | None = None


class PaymentRepo(Protocol):
    def find_by_key(self, user_id: str, key: str) -> PaymentRecord | None: ...
    def create(self, record: PaymentRecord) -> PaymentRecord: ...
    def save(self, record: PaymentRecord) -> None: ...


def new_reference() -> str:
    return "pay_" + secrets.token_hex(12)


def start_checkout(*, repo: PaymentRepo, router: GatewayRouter, gateways: Mapping[str, PaymentGateway],
                   user_id: str, email: str, amount: Money, country: str | None, idempotency_key: str,
                   success_url: str, cancel_url: str, preferred: str | None = None) -> PaymentRecord:
    if not amount.is_positive():
        raise CheckoutFailed("amount must be positive", retry_same_key=False)

    existing = repo.find_by_key(user_id, idempotency_key)
    if existing is not None:
        if existing.amount != amount:
            raise CheckoutFailed("this idempotency key was used for a different amount", retry_same_key=False)
        return existing                                  # a double click or a retry returns the same checkout

    record = repo.create(PaymentRecord(new_reference(), idempotency_key, user_id, amount))   # BEFORE any gateway call
    try:
        candidates = router.choose(currency=amount.currency, country=country, preferred=preferred)
    except NoGatewayError as exc:
        record.status = PaymentStatus.FAILED
        repo.save(record)
        raise CheckoutFailed(str(exc), retry_same_key=False) from exc

    attempts: list[str] = []
    for code in candidates:
        gateway = gateways[code]
        attempts.append(code)
        record.attempts = tuple(attempts)
        try:
            result: CheckoutResult = gateway.create_checkout(CheckoutRequest(
                reference=record.reference, amount=amount, email=email, success_url=success_url,
                cancel_url=cancel_url, idempotency_key=f"{idempotency_key}:{code}",
                metadata={"payment_reference": record.reference}))
        except GatewayRejected:
            router.health.record_failure(code)
            continue                                     # definitely nothing was created: try the next one
        except GatewayUncertain as exc:
            router.health.record_failure(code)
            record.provider = code                       # a session MAY exist there; remember where
            repo.save(record)
            raise CheckoutFailed("the payment provider did not answer; try again", retry_same_key=True) from exc
        router.health.record_success(code)
        record.provider, record.provider_ref, record.redirect_url = result.provider, result.provider_ref, result.redirect_url
        repo.save(record)
        return record

    record.status = PaymentStatus.FAILED
    repo.save(record)
    raise CheckoutFailed("no payment provider accepted the request", retry_same_key=False)
