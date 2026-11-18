from django.db import models


class TurnTraceRow(models.Model):
    """How a turn felt. No content. Joined to the ledger (UsageRecord) by assistant_message_id."""

    user_id = models.BigIntegerField(null=True, db_index=True)
    conversation_id = models.BigIntegerField(db_index=True)
    assistant_message_id = models.BigIntegerField(null=True, db_index=True)
    outcome = models.CharField(max_length=16)
    error_code = models.CharField(max_length=32, blank=True)
    first_token_ms = models.FloatField(null=True)
    total_ms = models.FloatField()
    chunks = models.PositiveIntegerField(default=0)
    output_chars = models.PositiveIntegerField(default=0)
    prompt_version = models.CharField(max_length=32, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
