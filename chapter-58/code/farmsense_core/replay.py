"""Replay a simulated three-day scenario through the alert rules and report how they behaved. The real rules smooth the data
(median of 5 readings) and someone acknowledges the heat-wave alert at 14:20; the naive rule does neither.

    python -m farmsense_core.replay

Day 1: two one-reading glitches (a loose cable). Day 2: a heat wave in the afternoon. Day 3: a 40-minute dropout and one more glitch.
A good rule set fires on the heat wave, stays silent on the glitches, and notices the dropout."""
from datetime import datetime, timedelta, timezone

from .alerts import ABOVE, NO_DATA, Rule, run_series
from .simulator import simulate_temperature

START = datetime(2026, 11, 9, tzinfo=timezone.utc)

RULES = [
    Rule("High temperature", ABOVE, 30.0, for_seconds=600, clear_threshold=29.0, severity="warning", cooldown_seconds=1800),
    Rule("Critical temperature", ABOVE, 33.0, for_seconds=300, clear_threshold=31.5, severity="critical", cooldown_seconds=900, escalate_after_seconds=900),
    Rule("Sensor offline", NO_DATA, for_seconds=900, severity="warning"),
]
ACK_AT = START + timedelta(days=1, hours=14, minutes=20)     # someone acknowledges during the heat wave
NAIVE = Rule("Naive (no wait, no hysteresis, 1-min reminders)", ABOVE, 30.0, for_seconds=0, cooldown_seconds=60)


def scenario():
    d = lambda day, h, m=0: START + timedelta(days=day, hours=h, minutes=m)
    return simulate_temperature(
        START, START + timedelta(days=3), 60, seed=11, mean=24.0, amplitude=4.0, noise=0.4,
        heat_waves=[(d(1, 12), d(1, 20), 9.0)],
        dropouts=[(d(2, 2), d(2, 2, 40))],
        spikes=[(d(0, 10), 25.0), (d(0, 15), 25.0), (d(2, 12), 25.0)])


def main() -> int:
    samples = scenario()
    print(f"{len(samples)} readings over 3 days; one every minute; spikes on day 1 and 3, heat wave on day 2, dropout on day 3\n")
    print(f"{'rule':<50}{'fire':>5}{'remind':>8}{'escal.':>8}{'resolve':>9}{'messages':>10}")
    all_events = {}
    for rule in RULES + [NAIVE]:
        real = rule is not NAIVE
        ev = run_series(rule, samples, smooth=5 if real else 1, ack_at=ACK_AT if real else None)
        all_events[rule.name] = ev
        count = lambda k: sum(1 for e in ev if e.kind == k)
        print(f"{rule.name:<50}{count('fire'):>5}{count('reminder'):>8}{count('escalate'):>8}{count('resolve'):>9}{len(ev):>10}")
    print("\nTimeline of the real rules (UTC):")
    timeline = sorted((e for r in RULES for e in all_events[r.name]), key=lambda e: e.at)
    for e in timeline:
        value = f" value {e.value:.1f}" if e.value is not None else ""
        print(f"  day {e.at.day - START.day + 1} {e.at:%H:%M}  {e.kind:<9}{e.rule}{value}")
    onset = next(ts for ts, v in samples if ts > START + timedelta(days=1, hours=12) and v > 30.0)
    first = lambda name: next(e.at for e in all_events[name] if e.kind == "fire" and e.at > START + timedelta(days=1))
    print(f"\nHeat wave: temperature first above 30 at day 2 {onset:%H:%M}.")
    print(f"  warning fired after {(first('High temperature') - onset).seconds // 60} min, critical after {(first('Critical temperature') - onset).seconds // 60} min.")
    spike_hours = {(0, 10), (0, 15), (2, 12)}
    alerted = [e for r in RULES[:2] for e in all_events[r.name] if e.kind == "fire" and (e.at.day - START.day, e.at.hour) in spike_hours]
    print(f"  glitches that triggered a real alert: {len(alerted)} of 3.   The naive rule fired {sum(e.kind == 'fire' for e in all_events[NAIVE.name])} times.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
