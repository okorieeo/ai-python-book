from django.utils import timezone

from .models import Plan, Subscription


def current_plan(user) -> Plan:
    """The plan that applies to this user right now. Fails closed to Free."""
    sub = Subscription.objects.select_related("plan").filter(user=user).first()
    if sub and sub.is_entitled(timezone.now()):
        return sub.plan
    return free_plan()


def free_plan() -> Plan:
    plan = Plan.objects.filter(code="free").first()
    return plan or Plan(code="free", name="Free", daily_message_limit=5)  # unsaved safety net
