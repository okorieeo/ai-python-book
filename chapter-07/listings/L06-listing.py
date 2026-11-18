from django.conf import settings
from django.db import models
from django.db.models import Q

class Plan(models.Model):
    class Interval(models.TextChoices):
        MONTH = "month", "Monthly"
        YEAR = "year", "Yearly"
        ONE_TIME = "one_time", "One time"

    code = models.SlugField(unique=True)
    name = models.CharField(max_length=100)
    price_cents = models.PositiveIntegerField()
    currency = models.CharField(max_length=3)
    billing_interval = models.CharField(max_length=10, choices=Interval.choices)
    monthly_token_limit = models.PositiveBigIntegerField()
    is_active = models.BooleanField(default=True)

    def __str__(self) -> str:
        return self.name

class Subscription(models.Model):
    class Status(models.TextChoices):
        TRIALING = "trialing"
        ACTIVE = "active"
        PAST_DUE = "past_due"
        CANCELED = "canceled"

    LIVE_STATUSES = [Status.TRIALING, Status.ACTIVE, Status.PAST_DUE]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="subscriptions")
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="subscriptions")
    provider = models.CharField(max_length=20)                      # "stripe" or "paystack"
    provider_subscription_id = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=Status.choices)
    current_period_end = models.DateTimeField(null=True, blank=True)
    cancel_at_period_end = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "provider_subscription_id"], name="uniq_provider_subscription"
            ),
            models.UniqueConstraint(
                fields=["user"],
                condition=Q(status__in=["trialing", "active", "past_due"]),
                name="one_live_subscription_per_user",
            ),
        ]

class WebhookEvent(models.Model):
    provider = models.CharField(max_length=20)
    event_id = models.CharField(max_length=255)
    event_type = models.CharField(max_length=100)
    payload = models.JSONField()
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["provider", "event_id"], name="uniq_provider_event")
        ]
