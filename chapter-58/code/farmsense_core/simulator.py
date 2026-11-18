"""A sensor simulator: realistic enough to test alert rules, reports and dashboards without a single device.
Deterministic: the same seed gives the same data, so tests and the examples in the book never change."""
import math
import random
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Sequence, Tuple

Point = Tuple[datetime, float]


def simulate_temperature(start: datetime, end: datetime, interval_s: int = 60, seed: int = 7, mean: float = 26.0, amplitude: float = 4.0,
                         noise: float = 0.25, heat_waves: Sequence[Tuple[datetime, datetime, float]] = (),
                         dropouts: Sequence[Tuple[datetime, datetime]] = (), spikes: Sequence[Tuple[datetime, float]] = ()) -> List[Point]:
    """Daily rhythm: coolest at 04:00, warmest at 16:00. `heat_waves` add up to +delta in a smooth bump,
    `dropouts` remove readings (a dead battery), `spikes` add a one-reading glitch (a loose cable)."""
    rnd = random.Random(seed)
    spike_map = {ts: delta for ts, delta in spikes}
    out, t = [], start
    while t < end:
        hours = t.hour + t.minute / 60.0
        v = mean + amplitude * math.sin((hours - 10.0) / 24.0 * 2 * math.pi) + rnd.gauss(0, noise)
        for w0, w1, delta in heat_waves:
            if w0 <= t < w1:
                x = (t - w0) / (w1 - w0)
                v += delta * math.sin(math.pi * x)
        v += spike_map.get(t, 0.0)
        if not any(d0 <= t < d1 for d0, d1 in dropouts):
            out.append((t, round(v, 1)))
        t += timedelta(seconds=interval_s)
    return out
