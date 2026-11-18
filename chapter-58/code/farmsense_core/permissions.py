"""Who may do what. Two questions are always asked together:  does the ROLE allow the action, and does the person's SCOPE
(the whole farm, or only some sites) cover the thing they are touching?  Every check lives in this one file so that it can
be tested exhaustively and cannot drift between the API, the WebSocket and the mobile app."""
from dataclasses import dataclass
from typing import FrozenSet, Iterable, Optional

OWNER, MANAGER, SUPERVISOR, WORKER, ADVISOR, VIEWER = "owner", "manager", "supervisor", "worker", "advisor", "viewer"
ROLES = (OWNER, MANAGER, SUPERVISOR, WORKER, ADVISOR, VIEWER)

# Actions that make sense for one site. Everything else is farm-wide and needs an unrestricted membership.
SITE_ACTIONS = frozenset({"dashboard.view", "alert.view", "alert.ack", "device.view", "insight.view", "insight.request", "readings.export"})

GRANTS = {
    VIEWER: {"dashboard.view", "alert.view", "report.view"},
    ADVISOR: {"dashboard.view", "alert.view", "report.view", "insight.view", "insight.request", "readings.export", "device.view"},
    WORKER: {"dashboard.view", "alert.view", "alert.ack", "device.view"},
    SUPERVISOR: {"dashboard.view", "alert.view", "alert.ack", "device.view", "report.view", "insight.view", "readings.export"},
    MANAGER: {"dashboard.view", "alert.view", "alert.ack", "alert.rule.manage", "device.view", "device.manage", "report.view",
              "report.configure", "insight.view", "insight.request", "readings.export", "member.view", "member.manage", "farm.update"},
}
GRANTS[OWNER] = GRANTS[MANAGER] | {"billing.manage", "farm.delete"}

ALL_ACTIONS = frozenset().union(*GRANTS.values())
ASSIGNABLE_BY = {OWNER: set(ROLES), MANAGER: {SUPERVISOR, WORKER, ADVISOR, VIEWER}}


@dataclass(frozen=True)
class Membership:
    role: str
    site_ids: Optional[FrozenSet[int]] = None       # None = the whole farm

    def __post_init__(self):
        if self.role not in ROLES:
            raise ValueError(f"unknown role {self.role!r}")


def can(m: Optional[Membership], action: str, site_id: Optional[int] = None) -> bool:
    if m is None or action not in ALL_ACTIONS:
        return False                                  # not a member, or an action nobody defined: deny by default
    if action not in GRANTS[m.role]:
        return False
    if m.site_ids is None:
        return True
    # a site-limited member: only site actions, and only on the sites they were given
    return action in SITE_ACTIONS and site_id is not None and site_id in m.site_ids


def visible_sites(m: Optional[Membership], all_site_ids: Iterable[int]) -> FrozenSet[int]:
    if m is None:
        return frozenset()
    ids = frozenset(all_site_ids)
    return ids if m.site_ids is None else ids & m.site_ids


def can_assign_role(actor: Optional[Membership], new_role: str) -> bool:
    """You may only hand out roles below your own: a manager cannot create a second manager or an owner."""
    return actor is not None and actor.site_ids is None and new_role in ASSIGNABLE_BY.get(actor.role, set())


def can_change_member(actor: Optional[Membership], target_role: str, new_role: Optional[str], owners: int) -> bool:
    """Change `target_role` to `new_role`, or remove the member when new_role is None. `owners` counts all owners of the farm."""
    if actor is None or actor.site_ids is not None or "member.manage" not in GRANTS.get(actor.role, set()):
        return False
    if target_role == OWNER and owners <= 1:
        return False                                  # a farm must never be left without an owner
    if target_role not in ASSIGNABLE_BY[actor.role]:
        return False                                  # you cannot touch someone at or above your level (except owners, who may)
    return new_role is None or new_role in ASSIGNABLE_BY[actor.role]
