"""Small statistics helpers shared by evals, monitoring and cost reports. Pure Python."""
from __future__ import annotations

import math
from typing import Sequence


def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """
    95% confidence interval for a pass rate. Unlike the textbook 'p +/- 2*sqrt(p(1-p)/n)' it behaves
    at small n and at rates near 0% or 100%, which is exactly where eval sets live.
    """
    if n <= 0:
        return (0.0, 1.0)
    if not 0 <= successes <= n:
        raise ValueError("successes must be between 0 and n")
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def percentile(values: Sequence[float], p: float) -> float:
    """Linear-interpolated percentile (p in 0..100). Empty input returns 0.0."""
    if not values:
        return 0.0
    if not 0 <= p <= 100:
        raise ValueError("p must be between 0 and 100")
    data = sorted(values)
    if len(data) == 1:
        return float(data[0])
    rank = (p / 100) * (len(data) - 1)
    lo, hi = math.floor(rank), math.ceil(rank)
    return float(data[lo] + (data[hi] - data[lo]) * (rank - lo))
