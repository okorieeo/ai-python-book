"""Small helpers shared by the test suites."""
from django.contrib.auth import get_user_model

from billing.models import Plan

PASSWORD = "a-long-test-password-1"


def make_user(email="ada@example.com"):
    return get_user_model().objects.create_user(email=email, password=PASSWORD)


def ensure_plans(free_limit=3, pro_limit=50):
    """Tests control the limits; migrations only seeded sensible defaults."""
    free, _ = Plan.objects.update_or_create(code="free", defaults=dict(
        name="Free", daily_message_limit=free_limit, sort_order=0))
    pro, _ = Plan.objects.update_or_create(code="pro", defaults=dict(
        name="Pro", daily_message_limit=pro_limit, price_usd_cents=1200, sort_order=1,
        stripe_price_id="price_pro_123", paystack_plan_code="PLN_pro_123", paystack_amount_minor=500000))
    return free, pro
