from django.conf import settings
from django.db import models


class UsageRecord(models.Model):
    """
    The billing ledger: one row per model call, written in the same transaction as the answer.
    It holds NO message content, so it can outlive both the conversation and (anonymised) the account.
    """

    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    conversation_id = models.BigIntegerField(null=True, db_index=True)   # plain ids: deleting a chat keeps the ledger
    message_id = models.BigIntegerField(null=True)
    model = models.CharField(max_length=64)
    prompt_version = models.CharField(max_length=32, blank=True)
    status = models.CharField(max_length=16)
    input_tokens = models.PositiveIntegerField(default=0)
    output_tokens = models.PositiveIntegerField(default=0)
    cache_write_tokens = models.PositiveIntegerField(default=0)
    cache_read_tokens = models.PositiveIntegerField(default=0)
    usage_estimated = models.BooleanField(default=False)      # True for cancelled / interrupted turns
    cost_micro_usd = models.BigIntegerField(null=True)        # NULL = model had no known price
    request_id = models.CharField(max_length=64, blank=True)  # the provider's id: quote it to support
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "created_at"], name="usage_user_day_idx"),
            models.Index(fields=["created_at"], name="usage_created_idx"),
        ]

# Add these to the Message model from Chapter 11 (adapt names to yours), then makemigrations:
#
#     status = models.CharField(max_length=16, default="complete")  # streaming|complete|truncated|refused|interrupted|cancelled|failed
#     stop_reason = models.CharField(max_length=40, blank=True)
#     model = models.CharField(max_length=64, blank=True)
#
# and to Conversation:
#
#     summary = models.TextField(blank=True)
