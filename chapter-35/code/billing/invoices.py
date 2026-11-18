"""Invoices and payments. An invoice is a record of what a customer owes for a period."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .entitlements import get_entitlements
from .models import Invoice, InvoiceLine, Payment, Subscription
from .pricing import Proration, format_money, overage_charge
from .registry import METERED_KEY, get_def
from .usage import used_in_window


def build_renewal_invoice(sub: Subscription, *, tax_rate_bps: int = 0) -> Invoice:
    """A draft invoice for the period that just ended: the plan price, plus any overage."""
    price = sub.price
    with transaction.atomic():
        invoice = Invoice.objects.create(
            user=sub.user,
            subscription=sub,
            currency=price.currency,
            period_start=sub.current_period_start,
            period_end=sub.current_period_end,
            tax_rate_bps=tax_rate_bps,
            provider=sub.provider,
        )
        InvoiceLine.objects.create(
            invoice=invoice,
            kind=InvoiceLine.Kind.SUBSCRIPTION,
            quantity=1,
            description=f"{sub.plan.name} ({price.interval}ly)",
            unit_amount_minor=price.amount_minor,
        )
        included = get_entitlements(sub.user, sub.current_period_start)[METERED_KEY].limit
        used = used_in_window(
            sub.user,
            get_def(METERED_KEY).usage_key,
            sub.current_period_start,
            sub.current_period_end,
        )
        blocks, _ = overage_charge(
            used, included, price.overage_unit_size, price.overage_unit_price_minor
        )
        if blocks:
            InvoiceLine.objects.create(
                invoice=invoice,
                kind=InvoiceLine.Kind.USAGE_OVERAGE,
                quantity=blocks,
                description=f"Extra AI messages: {used - included} over {included}, "
                f"in blocks of {price.overage_unit_size}",
                unit_amount_minor=price.overage_unit_price_minor,
            )
        invoice.recalculate()
    return invoice


def build_proration_invoice(
    sub: Subscription,
    proration: Proration,
    *,
    old_name: str,
    new_name: str,
    tax_rate_bps: int = 0,
) -> Invoice:
    with transaction.atomic():
        invoice = Invoice.objects.create(
            user=sub.user,
            subscription=sub,
            currency=sub.price.currency,
            period_start=sub.current_period_start,
            period_end=sub.current_period_end,
            tax_rate_bps=tax_rate_bps,
            provider=sub.provider,
        )
        InvoiceLine.objects.create(
            invoice=invoice,
            kind=InvoiceLine.Kind.PRORATION_CREDIT,
            quantity=1,
            description=f"Unused time on {old_name}",
            unit_amount_minor=-proration.credit_minor,
        )
        InvoiceLine.objects.create(
            invoice=invoice,
            kind=InvoiceLine.Kind.PRORATION_CHARGE,
            quantity=1,
            description=f"Remaining time on {new_name}",
            unit_amount_minor=proration.charge_minor,
        )
        invoice.recalculate()
    return invoice


def finalize(invoice: Invoice, *, now: Optional[datetime] = None) -> Invoice:
    """Issue a draft: it gets a number and its lines are locked."""
    if invoice.status != Invoice.Status.DRAFT:
        raise ValidationError("Only a draft can be finalized.")
    now = now or timezone.now()
    invoice.recalculate()
    invoice.status = Invoice.Status.OPEN
    invoice.issued_at = now
    invoice.number = f"INV-{now.year}-{invoice.pk:06d}"
    invoice.save(update_fields=["status", "issued_at", "number"])
    return invoice


def void(invoice: Invoice) -> Invoice:
    if invoice.status not in (Invoice.Status.DRAFT, Invoice.Status.OPEN):
        raise ValidationError("A paid invoice cannot be voided. Issue a credit instead.")
    invoice.status = Invoice.Status.VOID
    invoice.save(update_fields=["status"])
    return invoice


def record_payment(
    invoice: Invoice,
    *,
    provider: str,
    provider_payment_id: str,
    amount_minor: int,
    currency: str,
    status: str = Payment.Status.SUCCEEDED,
    now: Optional[datetime] = None,
) -> tuple[Payment, bool]:
    """Store a payment once, however many times the provider tells us about it."""
    if currency != invoice.currency:
        raise ValidationError(
            f"Payment is in {currency} but the invoice is in {invoice.currency}."
        )
    now = now or timezone.now()
    with transaction.atomic():
        invoice = Invoice.objects.select_for_update().get(pk=invoice.pk)
        payment, created = Payment.objects.get_or_create(
            provider=provider,
            provider_payment_id=provider_payment_id,
            defaults={
                "invoice": invoice,
                "amount_minor": amount_minor,
                "currency": currency,
                "status": status,
            },
        )
        if (
            created
            and status == Payment.Status.SUCCEEDED
            and invoice.status == Invoice.Status.OPEN
        ):
            paid = sum(
                p.amount_minor
                for p in invoice.payments.filter(status=Payment.Status.SUCCEEDED)
            )
            if paid >= invoice.total_minor:
                invoice.status = Invoice.Status.PAID
                invoice.paid_at = now
                invoice.save(update_fields=["status", "paid_at"])
    return payment, created


def describe(invoice: Invoice) -> list[str]:
    """Plain-text lines for an email or a PDF."""
    out = [f"Invoice {invoice.number or '(draft)'}"]
    for line in invoice.lines.all():
        out.append(
            f"  {line.description}  x{line.quantity}  {format_money(line.amount_minor, invoice.currency)}"
        )
    out.append(f"  Tax: {format_money(invoice.tax_minor, invoice.currency)}")
    out.append(f"  Total: {format_money(invoice.total_minor, invoice.currency)}")
    return out
