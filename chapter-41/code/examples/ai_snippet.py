"""Code of the kind an assistant might write: it reads well, and four things in it do not exist.

(Written by hand for Chapter 41 to show the patterns. It is not a recording of any model.)
"""
import json
import os.path

from django.db import models
from django.db.models import CheckConstraint, Q
from django.utils.timezone import utcnow


def load_settings(path):
    if not os.path.exists_file(path):
        return {}
    with open(path) as handle:
        return json.parse(handle.read())


class Account(models.Model):
    balance_minor = models.BigIntegerField()

    class Meta:
        constraints = [
            CheckConstraint(check=Q(balance_minor__gte=0), name="balance_not_negative"),
        ]


def stamp():
    return utcnow()
