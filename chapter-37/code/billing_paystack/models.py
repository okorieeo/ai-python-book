"""Paystack billing tables. If you built the data models of Chapter 35, add these fields to them instead.
Times are unix seconds. Amounts are whole numbers of the smallest unit (kobo, cents)."""
from django.conf import settings
from django.db import models

User = settings.AUTH_USER_MODEL


class PaystackCustomer(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="paystack_customer")
    customer_code = models.CharField(max_length=64, unique=True)       # CUS_...
    trial_used = models.BooleanField(default=False)


class PendingTransaction(models.Model):
    """A payment we started. It records what we EXPECT, so what Paystack reports can be compared with it."""

    reference = models.CharField(max_length=100, unique=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="+")
    plan_key = models.CharField(max_length=40)
    kind = models.CharField(max_length=24)
    amount = models.BigIntegerField()
    currency = models.CharField(max_length=3)
    status = models.CharField(max_length=12, default="pending", db_index=True)
    access_code = models.CharField(max_length=64, blank=True)
    created_at = models.FloatField(db_index=True)


class PaystackSubscription(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="paystack_subscription")
    customer_code = models.CharField(max_length=64)
    subscription_code = models.CharField(max_length=64, unique=True)
    email_token = models.CharField(max_length=64)                      # needed to cancel or resume; treat as a secret
    status = models.CharField(max_length=16, db_index=True)
    plan_key = models.CharField(max_length=40, blank=True, null=True)
    tier = models.CharField(max_length=10, default="free")
    next_payment_date = models.BigIntegerField(null=True, blank=True)
    authorization_code = models.CharField(max_length=64, blank=True)   # a saved card: treat as a secret too
    card_last4 = models.CharField(max_length=4, blank=True)
    trial_end = models.BigIntegerField(null=True, blank=True)
    pending_plan_key = models.CharField(max_length=40, blank=True, null=True)
    pending_subscription_code = models.CharField(max_length=64, blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)


class PaystackPayment(models.Model):
    ref = models.CharField(max_length=100, unique=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="paystack_payments")
    kind = models.CharField(max_length=24)
    amount = models.BigIntegerField()
    currency = models.CharField(max_length=3)
    status = models.CharField(max_length=12)
    created_at = models.DateTimeField(auto_now_add=True)


class CreditGrant(models.Model):
    ref = models.CharField(max_length=100, unique=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="paystack_credit_grants")
    amount = models.IntegerField()
    reversed = models.BooleanField(default=False)


class WebhookEvent(models.Model):
    """One row per distinct event body. Paystack events have no id, so the key is a hash of the bytes."""

    event_key = models.CharField(max_length=64, unique=True)
    event_type = models.CharField(max_length=80, db_index=True)
    status = models.CharField(max_length=12, db_index=True)
    attempts = models.PositiveSmallIntegerField(default=1)
    started_at = models.FloatField(default=0)
    error = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
