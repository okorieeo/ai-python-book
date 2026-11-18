"""The starting plans. Safe to run again: it updates by code instead of duplicating.

The prices below are examples to show the shape of a pricing table. They are not advice:
Section 35.7 shows how to test your own numbers against your AI costs before you publish any.
"""

from __future__ import annotations

from django.db import transaction

from .models import Plan, PlanEntitlement, Price

PLANS = [
    {
        "code": "free",
        "name": "Free",
        "tier": 0,
        "description": "Try it out.",
        "prices": [],
        "entitlements": {
            "ai.chat": True,
            "ai.agent_tools": False,
            "ai.premium_models": False,
            "ai.messages_per_month": 30,
            "chat.max_conversations": 5,
        },
    },
    {
        "code": "starter",
        "name": "Starter",
        "tier": 1,
        "description": "For individuals.",
        "prices": [
            ("USD", "month", 500, None, None),
            ("NGN", "month", 750_000, None, None),
        ],
        "entitlements": {
            "ai.chat": True,
            "ai.agent_tools": True,
            "ai.premium_models": False,
            "ai.messages_per_month": 300,
            "chat.max_conversations": 50,
        },
    },
    {
        "code": "pro",
        "name": "Pro",
        "tier": 2,
        "description": "For heavy daily use.",
        "prices": [
            ("USD", "month", 2900, 100, 150),
            ("NGN", "month", 4_500_000, 100, 250_000),
        ],
        "entitlements": {
            "ai.chat": True,
            "ai.agent_tools": True,
            "ai.premium_models": True,
            "ai.messages_per_month": 1500,
            "chat.max_conversations": None,
        },
    },
]


@transaction.atomic
def seed_default_plans() -> list[Plan]:
    out = []
    for spec in PLANS:
        plan, _ = Plan.objects.update_or_create(
            code=spec["code"],
            defaults={
                "name": spec["name"],
                "tier": spec["tier"],
                "description": spec["description"],
            },
        )
        for currency, interval, amount, unit, unit_price in spec["prices"]:
            Price.objects.update_or_create(
                plan=plan,
                currency=currency,
                interval=interval,
                is_active=True,
                defaults={
                    "amount_minor": amount,
                    "overage_unit_size": unit,
                    "overage_unit_price_minor": unit_price,
                },
            )
        for key, value in spec["entitlements"].items():
            if isinstance(value, bool):
                PlanEntitlement.objects.update_or_create(
                    plan=plan, key=key, defaults={"enabled": value, "limit": None}
                )
            else:
                PlanEntitlement.objects.update_or_create(
                    plan=plan, key=key, defaults={"enabled": True, "limit": value}
                )
        out.append(plan)
    return out
