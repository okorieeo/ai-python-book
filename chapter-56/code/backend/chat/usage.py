"""Daily message limits. The check and the increment are ONE database statement, so two tabs
cannot both slip through the last remaining message (Chapter 17.8, "atomic checks")."""
from dataclasses import dataclass
from datetime import date

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .models import UsageDay


@dataclass(frozen=True)
class Quota:
    allowed: bool
    used: int
    limit: int

    @property
    def remaining(self) -> int:
        return max(0, self.limit - self.used)


def _today() -> date:
    return timezone.now().date()  # the day resets at midnight UTC; a per-user time zone is an exercise


def try_consume_message(user, limit: int, today: date | None = None) -> Quota:
    today = today or _today()
    with transaction.atomic():
        UsageDay.objects.get_or_create(user=user, day=today)
        updated = UsageDay.objects.filter(user=user, day=today, messages__lt=limit).update(
            messages=F("messages") + 1)
        used = UsageDay.objects.values_list("messages", flat=True).get(user=user, day=today)
    return Quota(allowed=bool(updated), used=used, limit=limit)


def refund_message(user, today: date | None = None) -> None:
    """Give the message back when the model failed before saying anything. Never goes below zero."""
    UsageDay.objects.filter(user=user, day=today or _today(), messages__gt=0).update(messages=F("messages") - 1)


def add_tokens(user, input_tokens: int, output_tokens: int, today: date | None = None) -> None:
    UsageDay.objects.filter(user=user, day=today or _today()).update(
        input_tokens=F("input_tokens") + input_tokens, output_tokens=F("output_tokens") + output_tokens)


def get_quota(user, limit: int) -> Quota:
    used = UsageDay.objects.filter(user=user, day=_today()).values_list("messages", flat=True).first() or 0
    return Quota(allowed=used < limit, used=used, limit=limit)
