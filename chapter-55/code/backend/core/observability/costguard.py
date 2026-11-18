"""Watch what the AI provider will bill you, before the invoice does.

Reads usage rows (day, model, input_tokens, output_tokens) and a prices file YOU fill in from
the provider's pricing page (per MILLION tokens). Prices are never hard-coded: they change,
and a guard with stale prices is worse than none. Unknown models raise an alert instead of
silently costing zero.

    python backend/core/observability/costguard.py usage.csv prices.json --daily 20 --monthly 400
"""
from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True)
class Usage:
    day: date
    model: str
    input_tokens: int
    output_tokens: int


def load_usage(rows) -> list[Usage]:
    return [Usage(date.fromisoformat(r["day"]), r["model"], int(r["input_tokens"]), int(r["output_tokens"])) for r in rows]


def cost(usage: Usage, prices: dict) -> float | None:
    price = prices.get(usage.model)
    if not price:
        return None
    return usage.input_tokens / 1e6 * price["input"] + usage.output_tokens / 1e6 * price["output"]


def daily_totals(rows: list[Usage], prices: dict) -> tuple[dict, set]:
    totals: dict[date, float] = defaultdict(float)
    unknown: set[str] = set()
    for row in rows:
        value = cost(row, prices)
        if value is None:
            unknown.add(row.model)
        else:
            totals[row.day] += value
    return dict(totals), unknown


def projected_month(totals: dict, today: date, lookback: int = 7) -> float:
    """Spent so far this month + (average of the last `lookback` full days) x remaining days."""
    spent = sum(v for d, v in totals.items() if (d.year, d.month) == (today.year, today.month))
    recent = [totals.get(today - timedelta(days=i), 0.0) for i in range(1, lookback + 1)]
    average = sum(recent) / len(recent)
    next_month = date(today.year + (today.month == 12), today.month % 12 + 1, 1)
    remaining = (next_month - today).days - 1
    return spent + average * remaining


def evaluate(totals: dict, unknown: set, today: date, daily_budget: float, monthly_budget: float,
             spike_factor: float = 2.0, lookback: int = 7) -> list[str]:
    alerts = []
    if unknown:
        alerts.append(f"ALERT unknown_models: no price for {', '.join(sorted(unknown))}. Add them to prices.json.")
    today_cost = totals.get(today, 0.0)
    if today_cost > daily_budget:
        alerts.append(f"ALERT daily_budget: {today_cost:.2f} spent today (budget {daily_budget:.2f}).")
    projection = projected_month(totals, today, lookback)
    if projection > monthly_budget:
        alerts.append(f"ALERT monthly_projection: heading for {projection:.2f} this month (budget {monthly_budget:.2f}).")
    previous = [totals.get(today - timedelta(days=i), 0.0) for i in range(1, lookback + 1)]
    average = sum(previous) / len(previous)
    if average > 0 and today_cost > spike_factor * average:
        alerts.append(f"ALERT spike: today is {today_cost / average:.1f}x the {lookback}-day average.")
    return alerts


def main(argv=None, today: date | None = None, out=None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description="AI spend guard")
    parser.add_argument("usage_csv")
    parser.add_argument("prices_json")
    parser.add_argument("--daily", type=float, required=True)
    parser.add_argument("--monthly", type=float, required=True)
    args = parser.parse_args(argv)
    out = out or sys.stdout
    with open(args.usage_csv, newline="", encoding="utf-8") as handle:
        rows = load_usage(csv.DictReader(handle))
    with open(args.prices_json, encoding="utf-8") as handle:
        prices = json.load(handle)
    today = today or date.today()
    totals, unknown = daily_totals(rows, prices)
    alerts = evaluate(totals, unknown, today, args.daily, args.monthly)
    print(f"today {totals.get(today, 0.0):.2f} | projected month {projected_month(totals, today):.2f}", file=out)
    for alert in alerts:
        print(alert, file=out)
    return 1 if alerts else 0


if __name__ == "__main__":
    sys.exit(main())
