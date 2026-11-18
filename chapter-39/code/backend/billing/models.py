from django.db import models


class ProcessedWebhookEvent(models.Model):
    """One row per webhook event we have handled. The UNIQUE constraint is what makes 'once' true under concurrency."""
    key = models.CharField(max_length=200, unique=True)          # e.g. stripe:evt_123  or  paystack:charge.success:302961
    received_at = models.DateTimeField(auto_now_add=True)
