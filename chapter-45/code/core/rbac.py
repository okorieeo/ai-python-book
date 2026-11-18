"""Role-based access control as data: one matrix, deny by default, and a way to prove no action was forgotten."""
from __future__ import annotations

import enum


class Role(enum.StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


ACTIONS = (
    "conversation.read", "conversation.create", "conversation.delete",
    "message.send", "workspace.invite", "workspace.billing.read", "workspace.billing.manage", "workspace.delete",
)

PERMISSIONS: dict[Role, frozenset[str]] = {
    Role.VIEWER: frozenset({"conversation.read"}),
    Role.MEMBER: frozenset({"conversation.read", "conversation.create", "conversation.delete", "message.send"}),
    Role.ADMIN: frozenset({"conversation.read", "conversation.create", "conversation.delete", "message.send",
                           "workspace.invite", "workspace.billing.read"}),
    Role.OWNER: frozenset(ACTIONS),
}


def can(role: Role | str | None, action: str) -> bool:
    """Deny by default: unknown roles and unknown actions are never allowed."""
    try:
        return action in PERMISSIONS[Role(role)]
    except (KeyError, ValueError):
        return False


def matrix_gaps(routes: dict[str, str | None]) -> list[str]:
    """routes maps 'METHOD /path' to the action it requires. Returns problems: routes with no action, unknown actions."""
    problems = []
    for route, action in sorted(routes.items()):
        if not action:
            problems.append(f"{route}: no required action (it would be open to every signed-in user)")
        elif action not in ACTIONS:
            problems.append(f"{route}: unknown action {action!r}")
    return problems


def unused_actions(routes: dict[str, str | None]) -> list[str]:
    return sorted(set(ACTIONS) - {a for a in routes.values() if a})


def privilege_ladder_ok() -> bool:
    """Each higher role must include everything the lower one can do."""
    ladder = [Role.VIEWER, Role.MEMBER, Role.ADMIN, Role.OWNER]
    return all(PERMISSIONS[a] <= PERMISSIONS[b] for a, b in zip(ladder, ladder[1:]))
