"""Two read-only endpoints: the public pricing page, and "my plan and usage"."""

from __future__ import annotations

from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .entitlements import effective_plan, get_entitlements
from .models import Plan
from .registry import REGISTRY
from .usage import usage_summary


class PlanListView(APIView):
    """What a visitor sees before signing up. Only public, active plans."""

    permission_classes = [AllowAny]

    def get(self, request):
        plans = Plan.objects.filter(is_public=True, is_active=True).prefetch_related(
            "prices", "entitlements"
        )
        return Response(
            [
                {
                    "code": p.code,
                    "name": p.name,
                    "description": p.description,
                    "tier": p.tier,
                    "prices": [
                        {
                            "currency": pr.currency,
                            "interval": pr.interval,
                            "amount_minor": pr.amount_minor,
                        }
                        for pr in p.prices.all()
                        if pr.is_active
                    ],
                    "entitlements": [
                        {
                            "key": e.key,
                            "label": REGISTRY[e.key].label,
                            "enabled": e.enabled,
                            "limit": e.limit,
                        }
                        for e in p.entitlements.all()
                    ],
                }
                for p in plans
            ]
        )


class MyBillingView(APIView):
    """The signed-in user's own plan, entitlements and usage. Always filtered to request.user."""

    def get(self, request):
        user = request.user
        plan, sub = effective_plan(user)
        ents = get_entitlements(user)
        return Response(
            {
                "plan": {"code": plan.code, "name": plan.name},
                "subscription": (
                    None
                    if sub is None
                    else {
                        "status": sub.status,
                        "current_period_end": sub.current_period_end,
                        "cancel_at_period_end": sub.cancel_at_period_end,
                        "pending_plan": (
                            sub.pending_plan.code if sub.pending_plan_id else None
                        ),
                    }
                ),
                "entitlements": {
                    k: {"enabled": e.enabled, "limit": e.limit, "source": e.source}
                    for k, e in ents.items()
                },
                "usage": usage_summary(user),
            }
        )
