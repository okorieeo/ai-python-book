"""Billing data models.

Rules that run through every model here:
  * Money is stored as a whole number of the currency's smallest unit (kobo, cents).
    Never a float. A DecimalField is fine for display but not needed for storage.
  * Every amount has a currency next to it.
  * Records that describe what happened (usage, invoices, payments, webhook events)
    are never edited to "fix" history. You add a new record that corrects it.
  * Provider ids (Stripe, Paystack) are stored but are never the source of truth for
    what a user is entitled to. Our own tables are.
"""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q

from .registry import FEATURE, LIMIT, get_def


class Currency(models.TextChoices):
    NGN = "NGN", "Nigerian naira"
    USD = "USD", "US dollar"


class Interval(models.TextChoices):
    MONTH = "month", "Monthly"
    YEAR = "year", "Yearly"


class Provider(models.TextChoices):
    STRIPE = "stripe", "Stripe"
    PAYSTACK = "paystack", "Paystack"
    MANUAL = "manual", "Manual (set by staff)"


def default_currency() -> str:
    return settings.BILLING_DEFAULT_CURRENCY


# --------------------------------------------------------------------- customers
class BillingAccount(models.Model):
    """One per user. Holds billing preferences and is the row we lock when counting usage."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="billing_account"
    )
    currency = models.CharField(
        max_length=3, choices=Currency.choices, default=default_currency
    )
    country = models.CharField(
        max_length=2, blank=True
    )  # for tax rules (ask an accountant)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"BillingAccount({self.user_id}, {self.currency})"


# --------------------------------------------------------------------------- plans
class Plan(models.Model):
    """What a customer can choose. Prices live in Price; capabilities in PlanEntitlement."""

    code = models.SlugField(max_length=40, unique=True)
    name = models.CharField(max_length=80)
    description = models.TextField(blank=True)
    tier = models.PositiveSmallIntegerField(
        default=0, help_text="Higher tier = bigger plan."
    )
    is_public = models.BooleanField(default=True, help_text="Shown on the pricing page.")
    is_active = models.BooleanField(default=True, help_text="Can new customers pick it?")
    sort_order = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["tier", "sort_order", "id"]

    def __str__(self) -> str:
        return self.code


class Price(models.Model):
    """What a plan costs in one currency and interval. Prices are added, never edited."""

    plan = models.ForeignKey(Plan, on_delete=models.CASCADE, related_name="prices")
    currency = models.CharField(max_length=3, choices=Currency.choices)
    interval = models.CharField(
        max_length=10, choices=Interval.choices, default=Interval.MONTH
    )
    amount_minor = models.PositiveBigIntegerField(help_text="In kobo or cents.")
    # Hybrid pricing: an allowance is included, and extra usage is billed in blocks.
    overage_unit_size = models.PositiveIntegerField(null=True, blank=True)
    overage_unit_price_minor = models.PositiveBigIntegerField(null=True, blank=True)
    provider_ids = models.JSONField(
        default=dict,
        blank=True,
        help_text='e.g. {"stripe": "price_...", "paystack": "PLN_..."}',
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            # Only one live price per plan, currency and interval. Retire the old one, add a new one.
            models.UniqueConstraint(
                fields=["plan", "currency", "interval"],
                condition=Q(is_active=True),
                name="one_active_price_per_plan_currency_interval",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        overage_unit_size__isnull=True,
                        overage_unit_price_minor__isnull=True,
                    )
                    | Q(
                        overage_unit_size__isnull=False,
                        overage_unit_price_minor__isnull=False,
                    )
                ),
                name="overage_fields_come_together",
            ),
            models.CheckConstraint(
                condition=Q(overage_unit_size__isnull=True) | Q(overage_unit_size__gt=0),
                name="overage_unit_size_positive",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.plan.code} {self.amount_minor} {self.currency}/{self.interval}"


class PlanEntitlement(models.Model):
    """One capability a plan includes. The key must exist in billing.registry."""

    plan = models.ForeignKey(Plan, on_delete=models.CASCADE, related_name="entitlements")
    key = models.CharField(max_length=60)
    enabled = models.BooleanField(default=True)
    limit = models.PositiveBigIntegerField(
        null=True, blank=True, help_text="For limits only. Empty means unlimited."
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["plan", "key"], name="one_entitlement_per_plan_key"
            )
        ]

    def clean(self) -> None:
        definition = get_def(self.key)  # raises for unknown keys
        if definition.kind == FEATURE and self.limit is not None:
            raise ValidationError("A feature has no limit. Leave it empty.")
        if definition.kind == LIMIT and not self.enabled:
            raise ValidationError("To forbid a limit use 0. Leave 'enabled' on.")

    def save(self, *args, **kwargs):
        self.full_clean(exclude=["plan"])
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.plan.code}:{self.key}"


# ---------------------------------------------------------------- subscriptions
class Subscription(models.Model):
    class Status(models.TextChoices):
        TRIALING = "trialing"
        ACTIVE = "active"
        PAST_DUE = "past_due"  # a renewal payment failed; still in the grace window
        CANCELED = "canceled"  # ended because the customer cancelled
        EXPIRED = "expired"  # ended because it was not paid

    LIVE_STATUSES = (Status.TRIALING, Status.ACTIVE, Status.PAST_DUE)

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="subscriptions"
    )
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="subscriptions")
    price = models.ForeignKey(
        Price, on_delete=models.PROTECT, related_name="subscriptions"
    )
    status = models.CharField(max_length=12, choices=Status.choices)

    billing_anchor = (
        models.DateTimeField()
    )  # the first period started here; renewals keep its day
    period_number = models.PositiveIntegerField(default=0)
    current_period_start = models.DateTimeField()
    current_period_end = models.DateTimeField()
    trial_end = models.DateTimeField(null=True, blank=True)

    cancel_at_period_end = models.BooleanField(default=False)
    canceled_at = models.DateTimeField(null=True, blank=True)
    # A downgrade takes effect at the next renewal, not immediately.
    pending_plan = models.ForeignKey(
        Plan, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    pending_price = models.ForeignKey(
        Price, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )

    provider = models.CharField(max_length=12, choices=Provider.choices)
    provider_subscription_id = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            # The database itself refuses a second live subscription for one user.
            models.UniqueConstraint(
                fields=["user"],
                condition=Q(status__in=["trialing", "active", "past_due"]),
                name="one_live_subscription_per_user",
            ),
            models.UniqueConstraint(
                fields=["provider", "provider_subscription_id"],
                condition=~Q(provider_subscription_id=""),
                name="unique_provider_subscription_id",
            ),
            models.CheckConstraint(
                condition=Q(current_period_end__gt=F("current_period_start")),
                name="period_end_after_start",
            ),
        ]
        indexes = [models.Index(fields=["status", "current_period_end"])]

    def __str__(self) -> str:
        return f"Subscription({self.user_id}, {self.plan.code}, {self.status})"


class EntitlementOverride(models.Model):
    """A manual grant or restriction for one user: a promotion, a support gesture, a beta."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="entitlement_overrides",
    )
    key = models.CharField(max_length=60)
    enabled = models.BooleanField(default=True)
    limit = models.PositiveBigIntegerField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    reason = models.CharField(max_length=200)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self) -> None:
        get_def(self.key)

    def save(self, *args, **kwargs):
        self.full_clean(exclude=["user", "created_by"])
        super().save(*args, **kwargs)


# ------------------------------------------------------------------------ usage
class AppendOnlyError(RuntimeError):
    pass


class UsageEvent(models.Model):
    """One thing a user did that we may limit or bill. Written once, never changed."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="usage_events"
    )
    key = models.CharField(max_length=60)  # e.g. "ai.message"
    quantity = models.PositiveBigIntegerField(default=1)
    occurred_at = models.DateTimeField()
    # The caller makes this up from something stable (a request id). Same key = same event.
    idempotency_key = models.CharField(max_length=120, unique=True)
    cost_micro_usd = models.PositiveBigIntegerField(
        default=0, help_text="Our cost, in millionths of a dollar."
    )
    meta = models.JSONField(
        default=dict, blank=True
    )  # ids and model names, never message text

    class Meta:
        indexes = [models.Index(fields=["user", "key", "occurred_at"])]

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise AppendOnlyError(
                "Usage events are never changed. Add a correcting event instead."
            )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise AppendOnlyError("Usage events are never deleted.")


# --------------------------------------------------------------------- invoices
class Invoice(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft"  # lines can still change
        OPEN = "open"  # issued, waiting for payment
        PAID = "paid"
        VOID = "void"  # cancelled before payment

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="invoices"
    )
    subscription = models.ForeignKey(
        Subscription,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="invoices",
    )
    number = models.CharField(max_length=30, unique=True, blank=True, null=True)
    currency = models.CharField(max_length=3, choices=Currency.choices)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    period_start = models.DateTimeField(null=True, blank=True)
    period_end = models.DateTimeField(null=True, blank=True)
    tax_rate_bps = models.PositiveIntegerField(
        default=0, help_text="Basis points: 750 means 7.5%."
    )
    subtotal_minor = models.BigIntegerField(default=0)
    tax_minor = models.BigIntegerField(default=0)
    total_minor = models.BigIntegerField(default=0)
    issued_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    provider = models.CharField(max_length=12, choices=Provider.choices, blank=True)
    provider_invoice_id = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(total_minor=F("subtotal_minor") + F("tax_minor")),
                name="invoice_total_is_subtotal_plus_tax",
            )
        ]

    def recalculate(self) -> None:
        """Recompute totals from the lines. Allowed only while the invoice is a draft."""
        if self.status != self.Status.DRAFT:
            raise ValidationError("Only a draft invoice can be recalculated.")
        self.subtotal_minor = sum(line.amount_minor for line in self.lines.all())
        # Tax in whole minor units, rounded half up, on a basis-points rate.
        self.tax_minor = (
            (self.subtotal_minor * self.tax_rate_bps + 5_000) // 10_000
            if self.subtotal_minor > 0
            else 0
        )
        self.total_minor = self.subtotal_minor + self.tax_minor
        self.save(update_fields=["subtotal_minor", "tax_minor", "total_minor"])


class InvoiceLine(models.Model):
    class Kind(models.TextChoices):
        SUBSCRIPTION = "subscription"
        USAGE_OVERAGE = "usage_overage"
        PRORATION_CREDIT = "proration_credit"
        PRORATION_CHARGE = "proration_charge"
        ADJUSTMENT = "adjustment"

    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="lines")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    description = models.CharField(max_length=200)
    quantity = models.PositiveIntegerField(default=1)
    unit_amount_minor = models.BigIntegerField()  # negative for credits
    amount_minor = models.BigIntegerField()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(amount_minor=F("quantity") * F("unit_amount_minor")),
                name="line_amount_is_quantity_times_unit",
            )
        ]

    def save(self, *args, **kwargs):
        if self.invoice.status != Invoice.Status.DRAFT:
            raise ValidationError("Lines of an issued invoice cannot change.")
        self.amount_minor = self.quantity * self.unit_amount_minor
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.invoice.status != Invoice.Status.DRAFT:
            raise ValidationError("Lines of an issued invoice cannot be deleted.")
        return super().delete(*args, **kwargs)


class Payment(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending"
        SUCCEEDED = "succeeded"
        FAILED = "failed"
        REFUNDED = "refunded"

    invoice = models.ForeignKey(
        Invoice, on_delete=models.PROTECT, related_name="payments"
    )
    amount_minor = models.PositiveBigIntegerField()
    currency = models.CharField(max_length=3, choices=Currency.choices)
    status = models.CharField(max_length=10, choices=Status.choices)
    provider = models.CharField(max_length=12, choices=Provider.choices)
    provider_payment_id = models.CharField(max_length=120)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "provider_payment_id"], name="unique_provider_payment"
            )
        ]


class WebhookEvent(models.Model):
    """Every message a payment provider sends us, stored before we act on it (Chapter 36)."""

    class Status(models.TextChoices):
        RECEIVED = "received"
        PROCESSED = "processed"
        FAILED = "failed"

    provider = models.CharField(max_length=12, choices=Provider.choices)
    event_id = models.CharField(max_length=120)
    event_type = models.CharField(max_length=80)
    payload = models.JSONField()
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.RECEIVED
    )
    error = models.CharField(max_length=300, blank=True)
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "event_id"], name="unique_provider_event"
            )
        ]
