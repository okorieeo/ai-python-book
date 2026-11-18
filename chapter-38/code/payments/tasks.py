from datetime import timedelta

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from core.payments.reconciliation import Line, reconcile

from .models import Discrepancy, Payment, ReconciliationRun
from .registry import get_gateways
from .services import issue_invoice, sweep_pending


@shared_task(autoretry_for=(Exception,), retry_backoff=True, max_retries=5)
def after_payment_succeeded(reference: str) -> None:
    """Everything that must happen once, after the money is confirmed. Safe to run twice."""
    from django.conf import settings
    from billing.services import activate_for_payment          # Chapter 35: grants the plan or credits
    payment = Payment.objects.get(reference=reference)
    activate_for_payment(payment)                                # idempotent: keyed by payment.reference
    if not payment.invoices.filter(kind="invoice").exists():
        issue_invoice(payment, tax_rate_bp=settings.TAX_RATE_BP, prices_include_tax=settings.PRICES_INCLUDE_TAX)
    # email the receipt here (Chapter 22's email service), using payment.billing_email


@shared_task
def sweep_missed_webhooks() -> int:
    return sweep_pending()


@shared_task
def reconcile_gateway(provider: str, day_iso: str | None = None) -> int:
    """Daily: compare yesterday's settled payments with the gateway's own list. Returns the discrepancy count."""
    end = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    start = end - timedelta(days=1)
    gateway = get_gateways()[provider]
    theirs = gateway.list_transactions(start, end)
    mine = [Line(p.reference, p.amount_minor, p.currency, p.status, p.refunded_minor)
            for p in Payment.objects.filter(provider=provider, paid_at__gte=start, paid_at__lt=end,
                                            status__in=["succeeded", "partially_refunded", "refunded"])]
    report = reconcile(mine, theirs)
    with transaction.atomic():
        run = ReconciliationRun.objects.create(provider=provider, period_start=start, period_end=end,
                                               matched=report.matched, discrepancy_count=len(report.discrepancies))
        Discrepancy.objects.bulk_create([Discrepancy(run=run, kind=d.kind, reference=d.reference, detail=d.detail)
                                         for d in report.discrepancies])
    return len(report.discrepancies)
