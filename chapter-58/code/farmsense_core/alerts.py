"""The alert engine: decides WHEN a person should be told, and just as importantly when they should NOT be.

An alert system that cries wolf gets muted, and a muted alert system is worse than none. So every rule has:
  for_seconds         the condition must hold this long before we fire (a one-second spike is not an emergency)
  clear_threshold     hysteresis: once firing, the value must come back past a SEPARATE line to resolve (no flapping)
  cooldown_seconds    how often an unacknowledged alert may remind
  escalate_after      who else to wake up if nobody acknowledges
State is kept per (rule, sensor) and time is always passed in, so the engine is deterministic and easy to test."""
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Optional, Sequence, Tuple

OK, PENDING, FIRING = "ok", "pending", "firing"
ABOVE, BELOW, RATE_ABOVE, NO_DATA = "above", "below", "rate_above", "no_data"


@dataclass(frozen=True)
class Rule:
    name: str
    kind: str                           # above | below | rate_above | no_data
    threshold: float = 0.0              # for no_data this is ignored: for_seconds is the silence allowed
    for_seconds: int = 0
    clear_threshold: Optional[float] = None
    severity: str = "warning"           # warning | critical
    cooldown_seconds: int = 1800
    escalate_after_seconds: Optional[int] = None


@dataclass(frozen=True)
class Event:
    kind: str                           # fire | resolve | reminder | escalate
    at: datetime
    rule: str
    severity: str
    value: Optional[float]
    detail: str = ""


@dataclass
class Evaluator:
    rule: Rule
    state: str = OK
    since: Optional[datetime] = None            # when the condition first became true
    fired_at: Optional[datetime] = None
    last_notified: Optional[datetime] = None
    escalated: bool = False
    acknowledged: bool = False
    last_seen: Optional[datetime] = None
    prev: Optional[Tuple[datetime, float]] = None

    def acknowledge(self) -> None:
        self.acknowledged = True

    def _condition(self, now: datetime, value: Optional[float]) -> bool:
        r = self.rule
        if r.kind == NO_DATA:
            return self.last_seen is not None and (now - self.last_seen).total_seconds() >= max(r.for_seconds, 1)
        if value is None:
            return self.state == FIRING          # no new reading: keep the current verdict
        if r.kind == ABOVE:
            return value > r.threshold
        if r.kind == BELOW:
            return value < r.threshold
        if r.kind == RATE_ABOVE and self.prev is not None:
            seconds = (now - self.prev[0]).total_seconds()
            return seconds > 0 and (value - self.prev[1]) / seconds * 60.0 > r.threshold
        return False

    def _cleared(self, now: datetime, value: Optional[float]) -> bool:
        r = self.rule
        if r.kind == NO_DATA:
            return self.last_seen is not None and (now - self.last_seen).total_seconds() < max(r.for_seconds, 1)
        if value is None:
            return False
        line = r.clear_threshold if r.clear_threshold is not None else r.threshold
        if r.kind == ABOVE:
            return value <= line
        if r.kind == BELOW:
            return value >= line
        return not self._condition(now, value)

    def step(self, now: datetime, value: Optional[float] = None) -> List[Event]:
        """Call on every tick (or every reading). `value` is the newest reading, or None if nothing new arrived."""
        r, events = self.rule, []
        if value is not None:
            self.last_seen = now
        if self.state == FIRING:
            if self._cleared(now, value):
                events.append(Event("resolve", now, r.name, r.severity, value))
                self.state, self.since, self.fired_at, self.last_notified = OK, None, None, None
                self.escalated = self.acknowledged = False
            elif not self.acknowledged:
                if r.escalate_after_seconds is not None and not self.escalated \
                        and (now - self.fired_at).total_seconds() >= r.escalate_after_seconds:
                    self.escalated = True
                    events.append(Event("escalate", now, r.name, r.severity, value, "not acknowledged"))
                    self.last_notified = now
                elif (now - self.last_notified).total_seconds() >= r.cooldown_seconds:
                    events.append(Event("reminder", now, r.name, r.severity, value))
                    self.last_notified = now
        else:
            if self._condition(now, value):
                if self.state == OK:
                    self.state, self.since = PENDING, now
                # no_data is already a duration (for_seconds of silence), so it must not wait a second time
                if (now - self.since).total_seconds() >= (0 if r.kind == NO_DATA else r.for_seconds):
                    self.state, self.fired_at, self.last_notified = FIRING, now, now
                    events.append(Event("fire", now, r.name, r.severity, value))
            else:
                self.state, self.since = OK, None
        if value is not None:
            self.prev = (now, value)
        return events


def run_series(rule: Rule, samples: Sequence[Tuple[datetime, float]], tick_seconds: int = 60,
               end: Optional[datetime] = None, ack_at: Optional[datetime] = None, smooth: int = 1) -> List[Event]:
    """Replay a series through one rule, ticking every `tick_seconds` (a tick with no sample passes value=None).
    smooth > 1 first applies a median filter of that (odd) width, which removes one-reading glitches and calms noise near a threshold."""
    if not samples:
        return []
    if smooth > 1:
        from .aggregation import median_filter
        samples = list(zip([ts for ts, _ in samples], median_filter([v for _, v in samples], smooth)))
    ev, events = Evaluator(rule), []
    by_tick = {}
    for ts, v in samples:
        by_tick[int(ts.timestamp()) // tick_seconds] = v
    t = samples[0][0]
    stop = end or samples[-1][0]
    while t <= stop:
        events += ev.step(t, by_tick.get(int(t.timestamp()) // tick_seconds))
        if ack_at and t >= ack_at:
            ev.acknowledge()
        t += timedelta(seconds=tick_seconds)
    return events
