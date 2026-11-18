"""Stripe adapter. Thin on purpose: translate, do not decide."""
from datetime import datetime

import stripe
from django.conf import settings

from core.payments import normalize
from core.payments.gateway import (CheckoutRequest, CheckoutResult, GatewayRejected, GatewayUncertain, PaymentGateway,
                                   RefundResult, VerifiedPayment)
from core.payments.money import Money
from core.payments.reconciliation import Line
from core.payments.webhooks import verify_stripe_signature


class StripeGateway(PaymentGateway):
    code = "stripe"
    currencies = frozenset({"USD", "EUR", "GBP"})

    def __init__(self):
        self.api_key = settings.STRIPE_SECRET_KEY               # sk_test_... in development, from the environment
        self.webhook_secret = settings.STRIPE_WEBHOOK_SECRET    # whsec_..., one per endpoint

    def create_checkout(self, request: CheckoutRequest) -> CheckoutResult:
        try:
            session = stripe.checkout.Session.create(
                api_key=self.api_key, mode="payment", client_reference_id=request.reference,
                customer_email=request.email, success_url=request.success_url, cancel_url=request.cancel_url,
                line_items=[{"quantity": 1, "price_data": {
                    "currency": request.amount.currency.lower(), "unit_amount": request.amount.amount_minor,
                    "product_data": {"name": request.description or "Payment"}}}],
                metadata={"payment_reference": request.reference},
                payment_intent_data={"metadata": {"payment_reference": request.reference}},
                idempotency_key=request.idempotency_key, timeout=15)
        except stripe.error.InvalidRequestError as exc:          # 4xx: nothing was created
            raise GatewayRejected(str(exc)) from exc
        except (stripe.error.APIConnectionError, stripe.error.APIError, stripe.error.RateLimitError) as exc:
            raise GatewayUncertain(type(exc).__name__) from exc  # a session may exist: do not fail over
        return CheckoutResult(self.code, session.id, session.url)

    def verify(self, reference: str, provider_ref: str = "") -> VerifiedPayment:
        """provider_ref is the Checkout Session id we stored when the checkout was created."""
        session = stripe.checkout.Session.retrieve(provider_ref, api_key=self.api_key)
        status = "succeeded" if session.payment_status == "paid" else "pending"
        return VerifiedPayment(reference, status, Money(session.amount_total, session.currency.upper()),
                               session.payment_intent or session.id)

    def refund(self, *, reference: str, provider_ref: str, amount: Money, idempotency_key: str) -> RefundResult:
        try:
            refund = stripe.Refund.create(api_key=self.api_key, payment_intent=provider_ref,
                                          amount=amount.amount_minor, idempotency_key=idempotency_key,
                                          metadata={"payment_reference": reference})
        except stripe.error.InvalidRequestError as exc:
            raise GatewayRejected(str(exc)) from exc
        except (stripe.error.APIConnectionError, stripe.error.APIError) as exc:
            raise GatewayUncertain(type(exc).__name__) from exc
        return RefundResult(refund.id, "succeeded" if refund.status == "succeeded" else "pending", amount)

    def list_transactions(self, start: datetime, end: datetime) -> list:
        lines = []
        charges = stripe.Charge.list(api_key=self.api_key, limit=100, expand=["data.balance_transaction"],
                                     created={"gte": int(start.timestamp()), "lt": int(end.timestamp())})
        for charge in charges.auto_paging_iter():
            if not charge.paid or charge.status != "succeeded":
                continue
            if charge.amount_refunded >= charge.amount:
                status = "refunded"
            else:
                status = "partially_refunded" if charge.amount_refunded else "succeeded"
            fee = charge.balance_transaction.fee if charge.balance_transaction else 0
            ref = (charge.metadata or {}).get("payment_reference", charge.id)
            lines.append(Line(ref, charge.amount, charge.currency.upper(), status, charge.amount_refunded, fee))
        return lines

    def verify_webhook(self, raw_body: bytes, headers: dict, *, now: int) -> None:
        verify_stripe_signature(raw_body, headers.get("stripe-signature", ""), self.webhook_secret, now=now)

    def parse_webhook(self, raw_body: bytes):
        return normalize.parse_stripe(raw_body)
