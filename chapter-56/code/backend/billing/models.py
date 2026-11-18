from datetime import datetime, timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone


class Plan(models.Model):
    """What a customer can buy. Entitlements (limits) live here so a price change never needs a deploy."""

    code = models.SlugField(unique=True)  # "free", "pro"
    name = models.CharField(max_length=60)
    daily_message_limit = models.PositiveIntegerField()
    price_usd_cents = models.PositiveIntegerField(default=0)  # for display only
    period_days = models.PositiveSmallIntegerField(default=30)
    stripe_price_id = models.CharField(max_length=80, blank=True)
    paystack_plan_code = models.CharField(max_length=80, blank=True)
    paystack_amount_minor = models.PositiveBigIntegerField(null=True, blank=True)  # kobo/cents we expect to be paid
    is_public = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order"]

    def __str__(self) -> str:
        return self.name

    @property
    def is_paid(self) -> bool:
        return self.code != "free"

    def expected_amount(self, provider: str) -> int | None:
        return self.paystack_amount_minor if provider == "paystack" else None


class Subscription(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active"
        PAST_DUE = "past_due"
        CANCELED = "canceled"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="subscription")
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    gateway = models.CharField(max_length=20, blank=True)  # "stripe" or "paystack"
    external_customer_id = models.CharField(max_length=120, blank=True, db_index=True)
    external_subscription_id = models.CharField(max_length=120, blank=True, db_index=True)
    current_period_end = models.DateTimeField(null=True, blank=True)
    cancel_at_period_end = models.BooleanField(default=False)
    last_event_at = models.DateTimeField(null=True, blank=True)  # guards against out-of-order webhooks
    updated_at = models.DateTimeField(auto_now=True)

    def is_entitled(self, now: datetime | None = None) -> bool:
        """The ONE place that decides whether this subscription currently gives paid features."""
        now = now or timezone.now()
        if self.status == self.Status.ACTIVE:
            if self.cancel_at_period_end and self.current_period_end and now >= self.current_period_end:
                return False
            return True
        if self.status == self.Status.PAST_DUE and self.current_period_end:
            return now < self.current_period_end + timedelta(days=settings.BILLING_PAST_DUE_GRACE_DAYS)
        return False


class WebhookEvent(models.Model):
    """Every webhook we have processed. The unique constraint is what makes retries harmless."""

    provider = models.CharField(max_length=20)
    event_id = models.CharField(max_length=200)
    event_type = models.CharField(max_length=80)
    outcome = models.CharField(max_length=30, blank=True)
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["provider", "event_id"], name="one_row_per_provider_event")]
