import json
import os.path
from datetime import datetime, timezone

from django.db import models
from django.db.models import CheckConstraint, Q


def load_settings(path):
    if not os.path.exists(path):
        return {}
    with open(path) as handle:
        return json.loads(handle.read())


class Account(models.Model):
    balance_minor = models.BigIntegerField()

    class Meta:
        constraints = [CheckConstraint(condition=Q(balance_minor__gte=0), name="balance_not_negative")]


def stamp():
    return datetime.now(timezone.utc)
