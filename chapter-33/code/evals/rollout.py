"""Deterministic percentage rollouts: the same user always lands in the same bucket."""
from __future__ import annotations

import hashlib


def bucket(user_id: int | str, salt: str) -> int:
    """A stable number from 0 to 9999 for this user and this experiment."""
    digest = hashlib.sha256(f"{salt}:{user_id}".encode()).digest()
    return int.from_bytes(digest[:4], "big") % 10_000


def in_rollout(user_id: int | str, percent: float, salt: str) -> bool:
    """
    True for roughly `percent` of users. Raising the percent only ever ADDS users: someone in at 10% is still
    in at 25%, so nobody flips between old and new behaviour while you widen a rollout.
    """
    if not 0 <= percent <= 100:
        raise ValueError("percent must be between 0 and 100")
    return bucket(user_id, salt) < percent * 100
