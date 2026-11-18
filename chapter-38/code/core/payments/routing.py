"""Pick a gateway for each payment, and stop sending traffic to one that is failing."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable


class NoGatewayError(Exception):
    pass


@dataclass(frozen=True)
class GatewayConfig:
    code: str
    currencies: frozenset[str]
    home_countries: frozenset[str] = frozenset()   # where this gateway has local methods (bank, USSD, mobile money)
    priority: int = 100                            # lower is tried first
    enabled: bool = True


@dataclass
class HealthTracker:
    """A small circuit breaker: after `threshold` failures inside `window` seconds, skip the gateway for `cooldown`."""
    clock: Callable[[], float]
    threshold: int = 3
    window: float = 60.0
    cooldown: float = 120.0
    _failures: dict[str, list[float]] = field(default_factory=dict)
    _open_until: dict[str, float] = field(default_factory=dict)

    def record_failure(self, code: str) -> None:
        now = self.clock()
        recent = [t for t in self._failures.get(code, []) if now - t <= self.window] + [now]
        self._failures[code] = recent
        if len(recent) >= self.threshold:
            self._open_until[code] = now + self.cooldown
            self._failures[code] = []

    def record_success(self, code: str) -> None:
        self._failures.pop(code, None)
        self._open_until.pop(code, None)

    def is_open(self, code: str) -> bool:
        until = self._open_until.get(code)
        if until is None:
            return False
        if self.clock() >= until:
            self._open_until.pop(code, None)     # cooldown over: allow a trial request
            return False
        return True


class GatewayRouter:
    def __init__(self, configs: Iterable[GatewayConfig], health: HealthTracker):
        self.configs = list(configs)
        self.health = health

    def choose(self, *, currency: str, country: str | None, preferred: str | None = None,
               exclude: Iterable[str] = ()) -> list[str]:
        """Ordered candidates. First is the one to try; the rest are fallbacks for definite rejections only."""
        skip = set(exclude)
        eligible = [c for c in self.configs if c.enabled and currency in c.currencies and c.code not in skip]
        if not eligible:
            raise NoGatewayError(f"no gateway can charge {currency}")
        healthy = [c for c in eligible if not self.health.is_open(c.code)]
        pool = healthy or eligible          # if everything looks down, still try rather than refuse

        def rank(c: GatewayConfig):
            local = 0 if country and country in c.home_countries else 1
            wanted = 0 if preferred and c.code == preferred else 1
            return (wanted, local, c.priority, c.code)

        return [c.code for c in sorted(pool, key=rank)]
