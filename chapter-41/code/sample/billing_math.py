"""Small money helpers: the kind of code an assistant is often asked to write tests for.

All money is a whole number of the smallest unit (cents or kobo), as in Chapter 35.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional


def apply_discount(price_minor: int, percent: int) -> int:
    """Price after a percentage discount. The discount is rounded half up.

    >>> apply_discount(1000, 10)
    900
    >>> apply_discount(1005, 10)
    904
    """
    if not 0 <= percent <= 100:
        raise ValueError("percent must be between 0 and 100")
    if price_minor < 0:
        raise ValueError("price cannot be negative")
    discount = (price_minor * percent * 2 + 100) // 200
    return price_minor - discount


def split_evenly(total_minor: int, parts: int) -> list[int]:
    """Split money into parts that add up exactly. Earlier parts get the extra minor units.

    >>> split_evenly(100, 3)
    [34, 33, 33]
    """
    if parts < 1:
        raise ValueError("parts must be at least 1")
    if total_minor < 0:
        raise ValueError("total cannot be negative")
    base, extra = divmod(total_minor, parts)
    return [base + 1 if i < extra else base for i in range(parts)]


def overage_blocks(used: int, included: int, block_size: int) -> int:
    """How many started blocks of extra use to bill.

    >>> overage_blocks(1650, 1500, 100)
    2
    """
    if block_size < 1:
        raise ValueError("block_size must be at least 1")
    extra = max(0, used - included)
    return -(-extra // block_size)


def is_trial_active(now: datetime, trial_end: Optional[datetime]) -> bool:
    """A trial is active strictly before its end moment.

    >>> from datetime import datetime
    >>> is_trial_active(datetime(2026, 1, 1), datetime(2026, 2, 1))
    True
    """
    if trial_end is None:
        return False
    return now < trial_end


def prorate_credit(amount_minor: int, seconds_left: int, seconds_total: int) -> int:
    """Credit for the unused part of a period, rounded half up.

    >>> prorate_credit(500, 50, 100)
    250
    """
    if seconds_total <= 0:
        raise ValueError("seconds_total must be positive")
    left = max(0, min(seconds_left, seconds_total))
    return (amount_minor * left * 2 + seconds_total) // (seconds_total * 2)
