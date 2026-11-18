"""Money and price arithmetic. Pure functions: no database, easy to test.

All amounts are whole numbers of the currency's smallest unit (kobo, cents).
Rounding is always "half up", in integers, so results are the same on every machine.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Sequence

# Digits after the decimal point. Both are 2 today. Some currencies (the Japanese yen)
# have none: Chapter 36 shows how Stripe treats those, so never hard-code "divide by 100".
CURRENCY_EXPONENT = {"NGN": 2, "USD": 2}
CURRENCY_SYMBOL = {"NGN": "₦", "USD": "$"}


def format_money(amount_minor: int, currency: str) -> str:
    """For screens and emails only. Never parse this text back into a number."""
    exp = CURRENCY_EXPONENT[currency]
    sign = "-" if amount_minor < 0 else ""
    whole, frac = divmod(abs(amount_minor), 10**exp)
    return f"{sign}{CURRENCY_SYMBOL[currency]}{whole:,}.{frac:0{exp}d}"


def add_months(moment: datetime, months: int) -> datetime:
    """Add calendar months, keeping the day where possible (31 January + 1 month = 28 February)."""
    index = moment.month - 1 + months
    year, month = moment.year + index // 12, index % 12 + 1
    day = min(moment.day, calendar.monthrange(year, month)[1])
    return moment.replace(year=year, month=month, day=day)


def interval_months(interval: str) -> int:
    return {"month": 1, "year": 12}[interval]


def _ratio_round(value: int, numerator: int, denominator: int) -> int:
    """value * numerator / denominator, rounded half up, using only integers."""
    return (value * numerator * 2 + denominator) // (denominator * 2)


@dataclass(frozen=True)
class Proration:
    credit_minor: int  # unused part of the old plan, given back
    charge_minor: int  # the same remaining time on the new plan
    net_minor: (
        int  # charge - credit: what the customer owes now (negative = they are owed)
    )


def prorate(
    old_amount_minor: int,
    new_amount_minor: int,
    period_start: datetime,
    period_end: datetime,
    change_at: datetime,
) -> Proration:
    """Price a mid-period plan change by the share of the period still left (to the second)."""
    total = int((period_end - period_start).total_seconds())
    if total <= 0:
        raise ValueError("The period must have a positive length.")
    left = int((period_end - change_at).total_seconds())
    left = max(0, min(left, total))
    credit = _ratio_round(old_amount_minor, left, total)
    charge = _ratio_round(new_amount_minor, left, total)
    return Proration(credit, charge, charge - credit)


def overage_charge(
    used: int,
    included: Optional[int],
    unit_size: Optional[int],
    unit_price_minor: Optional[int],
) -> tuple[int, int]:
    """Hybrid pricing: an allowance is included; extra use is billed per started block.

    Returns (blocks, amount_minor). No allowance limit, or no overage price, means no charge.
    """
    if included is None or not unit_size or unit_price_minor is None:
        return 0, 0
    extra = max(0, used - included)
    blocks = -(-extra // unit_size)  # ceiling division
    return blocks, blocks * unit_price_minor


def graduated_price(quantity: int, tiers: Sequence[tuple[Optional[int], int]]) -> int:
    """Usage-based pricing where each band has its own unit price.

    tiers = [(first 1,000 units, price each), (next 9,000 units, price each), (the rest, price each)]
    Use None as the last band's size for "everything beyond".
    """
    remaining, total = quantity, 0
    for size, unit_price in tiers:
        take = remaining if size is None else min(remaining, size)
        total += take * unit_price
        remaining -= take
        if remaining <= 0:
            break
    return total


MICRO = 1_000_000  # our costs are tracked in millionths of a dollar


def unit_economics(
    *, price_minor: int, cost_micro_usd: int, fee_bps: int = 0, fixed_fee_minor: int = 0
) -> dict:
    """One customer-month in US dollars: revenue, provider fees, AI cost, and what is left.

    price_minor is in cents. The fee is the payment provider's cut, in basis points plus a
    fixed amount: look up your provider's current fees, they are not hard-coded here.
    """
    revenue_micro = price_minor * (MICRO // 100)
    fees_micro = (price_minor * fee_bps // 10_000 + fixed_fee_minor) * (MICRO // 100)
    profit_micro = revenue_micro - fees_micro - cost_micro_usd
    margin = profit_micro / revenue_micro if revenue_micro else 0.0
    return {
        "revenue_micro": revenue_micro,
        "fees_micro": fees_micro,
        "ai_cost_micro": cost_micro_usd,
        "profit_micro": profit_micro,
        "margin": margin,
    }
