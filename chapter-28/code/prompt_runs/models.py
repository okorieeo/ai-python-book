from django.db import models


class PromptRun(models.Model):
    """One model call: which prompt version, how big, how long. Never the prompt or reply text."""

    prompt_id = models.CharField(max_length=120, db_index=True)  # name@version#digest
    model = models.CharField(max_length=80, blank=True)
    input_tokens = models.PositiveIntegerField(default=0)
    output_tokens = models.PositiveIntegerField(default=0)
    latency_ms = models.PositiveIntegerField(default=0)
    attempts = models.PositiveSmallIntegerField(default=1)
    injection_risk = models.CharField(max_length=8, default="none")
    output_flagged = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.prompt_id} ({self.input_tokens}+{self.output_tokens} tokens)"
