"""The list of things a plan can grant. Defined in code, not in the database.

Adding a feature means adding a line here and checking it where the feature runs.
The database only says which plans include which of these keys.
"""

from __future__ import annotations

from dataclasses import dataclass

FEATURE = "feature"  # on or off
LIMIT = "limit"  # a number, or unlimited


@dataclass(frozen=True)
class EntitlementDef:
    key: str
    kind: str
    label: str
    period: str = (
        "none"  # for limits: "month", "day", or "none" (a stock you count yourself)
    )
    usage_key: str = ""  # which usage event key a metered limit adds up


REGISTRY: dict[str, EntitlementDef] = {
    d.key: d
    for d in [
        EntitlementDef("ai.chat", FEATURE, "AI chat"),
        EntitlementDef("ai.agent_tools", FEATURE, "Assistant can take actions"),
        EntitlementDef("ai.premium_models", FEATURE, "Premium AI models"),
        EntitlementDef(
            "ai.messages_per_month",
            LIMIT,
            "AI messages per month",
            period="month",
            usage_key="ai.message",
        ),
        EntitlementDef(
            "chat.max_conversations", LIMIT, "Saved conversations", period="none"
        ),
    ]
}

METERED_KEY = "ai.messages_per_month"


class UnknownEntitlement(KeyError):
    pass


def get_def(key: str) -> EntitlementDef:
    try:
        return REGISTRY[key]
    except KeyError:
        raise UnknownEntitlement(
            f"Unknown entitlement {key!r}. Known: {sorted(REGISTRY)}"
        ) from None
