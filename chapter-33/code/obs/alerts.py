"""
Alert rules over WindowMetrics, with two guards against noise:
  * min_samples: a rate computed from three turns is not evidence;
  * for_windows: a rule must be breached several evaluations in a row before anyone is paged.
"""
from __future__ import annotations

import operator
from dataclasses import dataclass, field

from .metrics import WindowMetrics

OPS = {">": operator.gt, "<": operator.lt}


@dataclass(frozen=True)
class Rule:
    name: str
    metric: str
    op: str
    threshold: float
    min_samples: int = 20
    for_windows: int = 2
    severity: str = "warn"           # warn | page

    def __post_init__(self):
        if self.op not in OPS:
            raise ValueError("op must be '>' or '<'")
        if not hasattr(WindowMetrics(), self.metric):
            raise ValueError(f"unknown metric {self.metric!r}")


@dataclass(frozen=True)
class Breach:
    rule: Rule
    value: float


def evaluate(rules: list[Rule], m: WindowMetrics) -> list[Breach]:
    out = []
    for rule in rules:
        value = getattr(m, rule.metric)
        if value is None or m.n < rule.min_samples:
            continue                        # no data is not a breach
        if OPS[rule.op](value, rule.threshold):
            out.append(Breach(rule, float(value)))
    return out


@dataclass
class AlertState:
    """Remembers how many windows in a row each rule has been breached."""
    streaks: dict[str, int] = field(default_factory=dict)
    firing: set[str] = field(default_factory=set)

    def update(self, rules: list[Rule], breaches: list[Breach]) -> tuple[list[Breach], list[str]]:
        """Returns (newly firing, newly resolved rule names)."""
        now = {b.rule.name: b for b in breaches}
        fired: list[Breach] = []
        resolved: list[str] = []
        for rule in rules:
            if rule.name in now:
                self.streaks[rule.name] = self.streaks.get(rule.name, 0) + 1
                if self.streaks[rule.name] >= rule.for_windows and rule.name not in self.firing:
                    self.firing.add(rule.name)
                    fired.append(now[rule.name])
            else:
                self.streaks[rule.name] = 0
                if rule.name in self.firing:
                    self.firing.discard(rule.name)
                    resolved.append(rule.name)
        return fired, resolved


def default_rules(*, hourly_budget_micro_usd: int | None = None) -> list[Rule]:
    rules = [
        Rule("error-rate", "error_rate", ">", 0.05, min_samples=30, severity="page"),
        Rule("slow-first-token", "p95_first_token_ms", ">", 8000, min_samples=30),
        Rule("refusals-up", "refusal_rate", ">", 0.05, min_samples=50),
        Rule("truncations-up", "truncation_rate", ">", 0.10, min_samples=50),
        Rule("unhappy-users", "thumbs_down_rate", ">", 0.25, min_samples=30),
        Rule("unpriced-model", "unpriced_calls", ">", 0, min_samples=1, for_windows=1, severity="page"),
    ]
    if hourly_budget_micro_usd is not None:
        rules.append(Rule("hourly-spend", "cost_micro_usd", ">", hourly_budget_micro_usd, min_samples=1,
                          for_windows=1, severity="page"))
    return rules
