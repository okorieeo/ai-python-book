from datetime import datetime, timezone

from django.contrib.auth import get_user_model
from django.test import TestCase

from billing.models import Price
from billing.seed import seed_default_plans

UTC = timezone.utc


def at(year, month, day, hour=12):
    return datetime(year, month, day, hour, tzinfo=UTC)


class BillingTestCase(TestCase):
    """Seeds the three default plans and gives each test a couple of users."""

    @classmethod
    def setUpTestData(cls):
        seed_default_plans()
        User = get_user_model()
        cls.alice = User.objects.create_user("alice", password="x")
        cls.bob = User.objects.create_user("bob", password="x")

    def price(self, plan_code, currency="USD", interval="month"):
        return Price.objects.get(plan__code=plan_code, currency=currency, interval=interval, is_active=True)
