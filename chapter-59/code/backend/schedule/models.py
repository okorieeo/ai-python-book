import uuid
from datetime import time

from django.conf import settings
from django.db import models


def default_work_days() -> list[int]:
    return [0, 1, 2, 3, 4]  # Monday to Friday


class PlannerPreferences(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="planner_preferences")
    # IANA name, e.g. Africa/Lagos
    timezone = models.CharField(max_length=64, default="UTC")
    work_start = models.TimeField(default=time(9, 0))
    work_end = models.TimeField(default=time(17, 0))
    work_days = models.JSONField(default=default_work_days)  # Monday=0 ... Sunday=6
    briefing_enabled = models.BooleanField(default=False)
    briefing_time = models.TimeField(default=time(7, 30))  # local time
    # local date of the last briefing sent
    last_briefing_on = models.DateField(null=True, blank=True)


class Event(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="events")
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    location = models.CharField(max_length=200, blank=True)
    # UTC; for a repeating event: the first occurrence
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()
    # zone the event lives in: repeats keep their wall-clock time here
    timezone = models.CharField(max_length=64)
    # see schedule/recurrence.py; NULL for one-off events
    recurrence = models.JSONField(null=True, blank=True)
    remind_minutes_before = models.PositiveSmallIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["start_at", "id"]
        indexes = [models.Index(fields=["user", "start_at"], name="event_user_start_idx")]
        constraints = [
            models.CheckConstraint(condition=models.Q(end_at__gt=models.F("start_at")), name="event_ends_after_start"),
        ]

    def __str__(self) -> str:
        return self.title
