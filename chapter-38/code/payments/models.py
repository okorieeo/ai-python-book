import uuid

from django.conf import settings
from django.db import models

from core.payments.states import PaymentStatus


class Payment(models.Model):
    """One attempt to collect money, whichever gateway handles it."""

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    reference = models.CharField(max_length=40, unique=True)          # sent to the gateway; webhooks echo it
    # SET_NULL: invoices and payments must outlive the account (tax law); Chapter 34's eraser anonymizes them.
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="payments")
    idempotency_key = models.CharField(max_length=80)
    kind = models.CharField(max_length=20, default="plan")            # plan | top_up | one_time (Chapter 35)
    plan_code = models.CharField(max_length=40, blank=True)
    amount_minor = models.BigIntegerField()
    currency = models.CharField(max_length=3)
    refunded_minor = models.BigIntegerField(default=0)
    status = models.CharField(max_length=20, choices=[(s.value, s.value) for s in PaymentStatus],
                              default=PaymentStatus.PENDING.value, db_index=True)
    provider = models.CharField(max_length=20, blank=True)            # "stripe" | "paystack"
    provider_ref = models.CharField(max_length=120, blank=True)
    redirect_url = models.URLField(max_length=1000, blank=True)
    attempts = models.JSONField(default=list)
    # Personal data kept only so an invoice can be issued; Chapter 34's eraser clears these three fields.
    billing_name = models.CharField(max_length=200, blank=True)
    billing_email = models.EmailField(blank=True)
    billing_address = models.TextField(blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "idempotency_key"], name="uniq_payment_user_key"),
            models.CheckConstraint(check=models.Q(amount_minor__gt=0), name="payment_amount_positive"),
            models.CheckConstraint(check=models.Q(refunded_minor__gte=0) & models.Q(refunded_minor__lte=models.F("amount_minor")),
                                   name="payment_refund_within_amount"),
        ]
        indexes = [models.Index(fields=["provider", "status", "created_at"])]


class WebhookEvent(models.Model):
    """Every verified delivery, stored once. The unique constraint IS the deduplication."""

    provider = models.CharField(max_length=20)
    event_id = models.CharField(max_length=120)
    raw_type = models.CharField(max_length=80)
    payload = models.TextField()                      # may contain an email; purged after 30 days (Chapter 34 rule)
    outcome = models.CharField(max_length=40, blank=True)
    error = models.CharField(max_length=200, blank=True)
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["provider", "event_id"], name="uniq_webhook_event")]


class Refund(models.Model):
    payment = models.ForeignKey(Payment, on_delete=models.PROTECT, related_name="refunds")
    amount_minor = models.BigIntegerField()
    reason = models.CharField(max_length=200)
    status = models.CharField(max_length=12, default="requested")    # requested | submitted | succeeded | failed
    provider_ref = models.CharField(max_length=120, blank=True)
    idempotency_key = models.CharField(max_length=120, unique=True)
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)


class InvoiceSequence(models.Model):
    """One row per prefix and year. Locked with select_for_update so numbers never repeat or skip."""

    prefix = models.CharField(max_length=10)
    year = models.PositiveIntegerField()
    last_value = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["prefix", "year"], name="uniq_invoice_sequence")]


class Invoice(models.Model):
    """Append-only. A mistake is corrected with a credit note, never an edit."""

    class Kind(models.TextChoices):
        INVOICE = "invoice"
        CREDIT_NOTE = "credit_note"

    number = models.CharField(max_length=30, unique=True)
    kind = models.CharField(max_length=12, choices=Kind.choices, default=Kind.INVOICE)
    payment = models.ForeignKey(Payment, on_delete=models.PROTECT, related_name="invoices")
    original = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="credit_notes")
    currency = models.CharField(max_length=3)
    net_minor = models.BigIntegerField()
    tax_minor = models.BigIntegerField()
    gross_minor = models.BigIntegerField()
    tax_rate_bp = models.PositiveIntegerField()
    lines = models.JSONField()
    seller_snapshot = models.JSONField()              # name, address, tax id at the time of issue
    buyer_snapshot = models.JSONField()               # cleared by the Chapter 34 eraser when the person is erased
    issued_at = models.DateTimeField()

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise PermissionError("Issued invoices are immutable; issue a credit note instead.")
        super().save(*args, **kwargs)


class ReconciliationRun(models.Model):
    provider = models.CharField(max_length=20)
    period_start = models.DateTimeField()
    period_end = models.DateTimeField()
    matched = models.PositiveIntegerField(default=0)
    discrepancy_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)


class Discrepancy(models.Model):
    run = models.ForeignKey(ReconciliationRun, on_delete=models.CASCADE, related_name="discrepancies")
    kind = models.CharField(max_length=30)
    reference = models.CharField(max_length=120)
    detail = models.CharField(max_length=300)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    note = models.CharField(max_length=300, blank=True)
