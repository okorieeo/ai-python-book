"""Billing tables. If you built the data models of Chapter 35, add these fields to them instead of
creating a second set. Times are unix seconds, exactly as Stripe sends them."""
from django.conf import settings
from django.db import models

User = settings.AUTH_USER_MODEL


class StripeCustomer(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="stripe_customer")
    customer_id = models.CharField(max_length=64, unique=True)
    trial_used = models.BooleanField(default=False)          # one free trial per user, ever
    created_at = models.DateTimeField(auto_now_add=True)


class StripeSubscription(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="stripe_subscription")
    customer_id = models.CharField(max_length=64)
    subscription_id = models.CharField(max_length=64, unique=True)
    status = models.CharField(max_length=24, db_index=True)
    plan_key = models.CharField(max_length=40, blank=True, null=True)
    tier = models.CharField(max_length=10, default="free")
    price_id = models.CharField(max_length=64, blank=True)
    period_end = models.BigIntegerField(null=True, blank=True)
    cancel_at_period_end = models.BooleanField(default=False)
    cancel_at = models.BigIntegerField(null=True, blank=True)
    trial_end = models.BigIntegerField(null=True, blank=True)
    canceled_at = models.BigIntegerField(null=True, blank=True)
    past_due_since = models.BigIntegerField(null=True, blank=True)
    last_event_created = models.BigIntegerField(default=0)    # newest Stripe event applied
    updated_at = models.DateTimeField(auto_now=True)


class StripePayment(models.Model):
    ref = models.CharField(max_length=64, unique=True)        # PaymentIntent id or invoice id
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="stripe_payments")
    kind = models.CharField(max_length=24)
    amount = models.BigIntegerField()                         # smallest currency unit
    currency = models.CharField(max_length=3)
    status = models.CharField(max_length=12)
    fulfil_ref = models.CharField(max_length=64, blank=True)
    receipt_url = models.URLField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class CreditGrant(models.Model):
    ref = models.CharField(max_length=64, unique=True)        # the checkout session id: the idempotency key
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="credit_grants")
    amount = models.IntegerField()
    reversed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)


class WebhookEvent(models.Model):
    """One row per Stripe event id. The unique id is what makes duplicate deliveries harmless."""

    event_id = models.CharField(max_length=64, unique=True)
    event_type = models.CharField(max_length=80, db_index=True)
    status = models.CharField(max_length=12, db_index=True)   # processing, processed, failed, ignored
    attempts = models.PositiveSmallIntegerField(default=1)
    started_at = models.FloatField(default=0)
    error = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
