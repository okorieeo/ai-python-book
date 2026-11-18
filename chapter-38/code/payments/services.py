import logging
import time
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from audit.services import Action, record as audit
from core.payments.checkout import start_checkout
from core.payments.events import apply_event
from core.payments.gateway import GatewayRejected, GatewayUncertain, NormalizedEvent
from core.payments.invoices import Line, credit_note_totals, invoice_number, totals_for
from core.payments.money import Money
from core.payments.refunds import RefundPolicy, refund_idempotency_key, validate_refund
from core.payments.states import PaymentStatus

from .models import Invoice, InvoiceSequence, Payment, Refund, WebhookEvent
from .registry import get_gateways, get_router
from .repo import DjangoPaymentRepo

logger = logging.getLogger(__name__)


def begin_checkout(*, user, plan_code: str, currency: str, country: str | None, idempotency_key: str,
                   preferred: str | None = None):
    """The price comes from OUR catalogue (Chapter 35), never from the request body."""
    from billing.services import price_for           # Chapter 35: returns a core.payments.money.Money
    amount: Money = price_for(plan_code, currency)
    repo = DjangoPaymentRepo(plan_code=plan_code, billing_email=user.email)
    return start_checkout(repo=repo, router=get_router(), gateways=get_gateways(), user_id=user.pk, email=user.email,
                          amount=amount, country=country, idempotency_key=idempotency_key,
                          success_url=f"{settings.FRONTEND_URL}/billing/return", cancel_url=f"{settings.FRONTEND_URL}/billing",
                          preferred=preferred)


def handle_webhook(provider: str, raw_body: bytes, headers: dict) -> tuple[int, str]:
    """Return (http_status, outcome). Bad signatures are 400; our own failures are 500 so the gateway retries."""
    gateway = get_gateways().get(provider)
    if gateway is None:
        return 404, "unknown_provider"
    from core.payments.gateway import SignatureError
    try:
        gateway.verify_webhook(raw_body, headers, now=int(time.time()))
    except SignatureError:
        logger.warning("webhook rejected", extra={"event": "webhook_bad_signature", "fields": {"provider": provider}})
        return 400, "bad_signature"
    event = gateway.parse_webhook(raw_body)
    return 200, process_event(event, raw_body)   # 200 even for unknown references: retries would not help


def process_event(event: NormalizedEvent, raw_body: bytes = b"") -> str:
    """Store the delivery once, apply it once, and queue the side effects only after the commit."""
    try:
        with transaction.atomic():
            stored, created = WebhookEvent.objects.get_or_create(
                provider=event.provider, event_id=event.event_id,
                defaults={"raw_type": event.raw_type, "payload": raw_body.decode("utf-8", "replace")[:20000]})
            if not created and stored.processed_at:
                return "duplicate"                     # the unique constraint is the deduplication
            if event.reference:                        # lock the row so two events for one payment queue up
                Payment.objects.select_for_update().filter(reference=event.reference).first()
            outcome = apply_event(event, DjangoPaymentRepo(), now=timezone.now())
            if outcome == "fulfilled" and event.provider_ref:
                Payment.objects.filter(reference=event.reference).update(provider_ref=event.provider_ref)
            stored.outcome, stored.processed_at = outcome, timezone.now()
            stored.save(update_fields=["outcome", "processed_at"])
            if outcome == "fulfilled":
                transaction.on_commit(lambda: after_payment_succeeded_task(event.reference))
            elif outcome == "amount_mismatch":
                logger.error("amount mismatch", extra={"event": "payment_amount_mismatch",
                             "fields": {"provider": event.provider, "reference": event.reference}})
            return outcome
    except IntegrityError:
        return "duplicate"                             # two deliveries raced; the other one wins


def after_payment_succeeded_task(reference: str) -> None:
    from .tasks import after_payment_succeeded
    after_payment_succeeded.delay(reference)


def issue_invoice(payment: Payment, *, tax_rate_bp: int, prices_include_tax: bool) -> Invoice:
    from billing.services import describe_purchase   # Chapter 35: description for the invoice line
    now = timezone.now()
    lines = [Line(describe_purchase(payment), 1, Money(payment.amount_minor, payment.currency))]
    totals = totals_for(lines, tax_rate_bp, prices_include_tax=prices_include_tax)
    with transaction.atomic():
        seq, _ = InvoiceSequence.objects.select_for_update().get_or_create(prefix=settings.INVOICE_PREFIX, year=now.year)
        seq.last_value += 1
        seq.save(update_fields=["last_value"])
        return Invoice.objects.create(
            number=invoice_number(settings.INVOICE_PREFIX, now.year, seq.last_value), payment=payment,
            currency=payment.currency, net_minor=totals.net.amount_minor, tax_minor=totals.tax.amount_minor,
            gross_minor=totals.gross.amount_minor, tax_rate_bp=tax_rate_bp,
            lines=[{"description": l.description, "quantity": l.quantity, "unit_minor": l.unit_price.amount_minor} for l in lines],
            seller_snapshot=settings.SELLER_DETAILS,
            buyer_snapshot={"name": payment.billing_name, "email": payment.billing_email, "address": payment.billing_address},
            issued_at=now)


def refund_payment(*, staff_user, payment: Payment, amount: Money, reason: str, override: bool = False) -> Refund:
    """Validate, record the intent, call the gateway, and let the webhook confirm. Safe to retry."""
    with transaction.atomic():
        locked = Payment.objects.select_for_update().get(pk=payment.pk)
        total, done = Money(locked.amount_minor, locked.currency), Money(locked.refunded_minor, locked.currency)
        validate_refund(status=PaymentStatus(locked.status), paid_at=locked.paid_at, now=timezone.now(), total=total,
                        already_refunded=done, requested=amount, policy=RefundPolicy(), staff_override=override)
        key = refund_idempotency_key(locked.reference, done, amount)
        refund, created = Refund.objects.get_or_create(
            idempotency_key=key, defaults={"payment": locked, "amount_minor": amount.amount_minor, "reason": reason[:200],
                                           "requested_by": staff_user})
    if not created and refund.status in ("submitted", "succeeded"):
        return refund                                    # a retry of something already sent
    gateway = get_gateways()[locked.provider]
    try:
        result = gateway.refund(reference=locked.reference, provider_ref=locked.provider_ref, amount=amount, idempotency_key=key)
    except GatewayRejected:
        refund.status = "failed"; refund.save(update_fields=["status"])
        raise
    except GatewayUncertain:
        raise                                            # leave it "requested"; reconciliation or a retry settles it
    refund.status, refund.provider_ref = "submitted", result.provider_ref
    refund.save(update_fields=["status", "provider_ref"])
    audit(Action.PAYMENT_REFUND_REQUESTED, actor=staff_user, metadata={"payment": locked.reference, "amount": amount.amount_minor})
    return refund


def sweep_pending(max_age_minutes: int = 15, give_up_hours: int = 48) -> int:
    """Catch payments whose webhook never arrived: ask the gateway directly and apply the answer the normal way."""
    now = timezone.now()
    stale = Payment.objects.filter(status=PaymentStatus.PENDING.value, provider__gt="",
                                   created_at__lte=now - timedelta(minutes=max_age_minutes),
                                   created_at__gte=now - timedelta(hours=give_up_hours))
    fixed = 0
    for payment in stale:
        gateway = get_gateways().get(payment.provider)
        if gateway is None:
            continue
        try:
            verified = gateway.verify(payment.reference, payment.provider_ref)
        except (GatewayRejected, GatewayUncertain):
            continue
        if verified.status == "succeeded":
            event = NormalizedEvent(payment.provider, f"sweep:{payment.reference}", "payment_succeeded", payment.reference,
                                    provider_ref=verified.provider_ref, amount_minor=verified.amount.amount_minor,
                                    currency=verified.amount.currency)
            fixed += process_event(event) == "fulfilled"
    return fixed
