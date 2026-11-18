from django.conf import settings
from django.db import models


class MessageFeedback(models.Model):
    """One rating per person per answer. Content lives on the message; this row holds only the judgement."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    message = models.ForeignKey("chat.Message", on_delete=models.CASCADE, related_name="feedback")
    conversation_id = models.BigIntegerField(db_index=True)
    rating = models.SmallIntegerField()                       # +1 or -1
    reason = models.CharField(max_length=16, blank=True)
    comment = models.CharField(max_length=500, blank=True)    # scrubbed before saving
    may_use_for_improvement = models.BooleanField(default=False)   # explicit opt-in (Chapters 26 and 34)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "message"], name="one_feedback_per_user_per_message")]
        indexes = [models.Index(fields=["rating", "created_at"], name="feedback_rating_day_idx")]
