"""Data model for the farm monitoring platform.  (Django layer: written for this chapter, NOT executed in the book's test
environment, which had no Django or PostgreSQL. It is syntax-checked only. See the README.)

Raw readings are NOT a Django model: they live in a partitioned table created by SQL (migrations/0002_readings.py) and are
written and read with raw SQL (readings_sql.py), because an ORM row per reading is far too heavy at this volume."""
from django.conf import settings
from django.db import models

from farmsense_core.permissions import ROLES, Membership as CoreMembership


class Farm(models.Model):
    name = models.CharField(max_length=120)
    timezone = models.CharField(max_length=64, default="UTC")      # reports are cut at the FARM's midnight, not the server's
    created_at = models.DateTimeField(auto_now_add=True)


class Site(models.Model):
    farm = models.ForeignKey(Farm, on_delete=models.CASCADE, related_name="sites")
    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=20, choices=[("barn", "Barn"), ("greenhouse", "Greenhouse"), ("field", "Field")], default="barn")


class Membership(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="farm_memberships")
    farm = models.ForeignKey(Farm, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=12, choices=[(r, r) for r in ROLES])
    # An explicit flag, NOT "an empty site list means everything". With the second design, deleting the last site of a
    # restricted worker silently promotes them to the whole farm.
    all_sites = models.BooleanField(default=True)
    sites = models.ManyToManyField(Site, blank=True, related_name="+")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "farm"], name="one_membership_per_farm")]

    def to_core(self) -> CoreMembership:
        return CoreMembership(self.role, None if self.all_sites else frozenset(self.sites.values_list("id", flat=True)))


class Device(models.Model):
    farm = models.ForeignKey(Farm, on_delete=models.CASCADE, related_name="devices")
    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name="devices")
    name = models.CharField(max_length=120)
    key_id = models.CharField(max_length=12, unique=True)
    key_hash = models.CharField(max_length=64)                      # only the hash is stored; the key itself is shown once
    last_seen_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)


class Sensor(models.Model):
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name="sensors")
    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name="sensors")
    key = models.CharField(max_length=64, unique=True)              # what the device sends, e.g. "barn1-temp"
    name = models.CharField(max_length=120)
    type = models.CharField(max_length=20)                          # a key of farmsense_core.sensors.SENSOR_TYPES
    interval_s = models.PositiveIntegerField(default=60)
    high_limit = models.FloatField(null=True, blank=True)
    low_limit = models.FloatField(null=True, blank=True)


class AlertRule(models.Model):
    sensor = models.ForeignKey(Sensor, on_delete=models.CASCADE, related_name="rules")
    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=12, choices=[("above", "above"), ("below", "below"), ("rate_above", "rate_above"), ("no_data", "no_data")])
    threshold = models.FloatField(default=0)
    for_seconds = models.PositiveIntegerField(default=0)
    clear_threshold = models.FloatField(null=True, blank=True)
    severity = models.CharField(max_length=10, choices=[("warning", "warning"), ("critical", "critical")], default="warning")
    cooldown_seconds = models.PositiveIntegerField(default=1800)
    escalate_after_seconds = models.PositiveIntegerField(null=True, blank=True)
    enabled = models.BooleanField(default=True)


class AlertState(models.Model):
    """The engine's memory between ticks (the Evaluator of farmsense_core.alerts, saved after every step)."""
    rule = models.OneToOneField(AlertRule, on_delete=models.CASCADE, related_name="state")
    state = models.CharField(max_length=8, default="ok")
    since = models.DateTimeField(null=True)
    fired_at = models.DateTimeField(null=True)
    last_notified = models.DateTimeField(null=True)
    escalated = models.BooleanField(default=False)
    acknowledged = models.BooleanField(default=False)
    last_seen = models.DateTimeField(null=True)
    prev_ts = models.DateTimeField(null=True)
    prev_value = models.FloatField(null=True)


class Alert(models.Model):
    """The history people read: one row per episode, from firing to resolution."""
    rule = models.ForeignKey(AlertRule, on_delete=models.CASCADE, related_name="alerts")
    started_at = models.DateTimeField()
    resolved_at = models.DateTimeField(null=True, blank=True)
    peak_value = models.FloatField(null=True)
    acknowledged_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    acknowledged_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-started_at"]


class PushToken(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="push_tokens")
    token = models.CharField(max_length=200, unique=True)           # "ExponentPushToken[...]"
    platform = models.CharField(max_length=10, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class DailyReport(models.Model):
    farm = models.ForeignKey(Farm, on_delete=models.CASCADE, related_name="reports")
    day = models.DateField()                                        # the farm's LOCAL calendar day
    pdf = models.FileField(upload_to="reports/%Y/%m/")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["farm", "day"], name="one_report_per_day")]   # makes the task safe to run twice


class DailyInsight(models.Model):
    farm = models.ForeignKey(Farm, on_delete=models.CASCADE, related_name="insights")
    day = models.DateField()
    facts = models.JSONField(default=list)                          # exactly what the model was shown
    summary = models.TextField()
    recommendations = models.JSONField(default=list)
    model = models.CharField(max_length=64, blank=True)
    fallback = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["farm", "day"], name="one_insight_per_day")]
