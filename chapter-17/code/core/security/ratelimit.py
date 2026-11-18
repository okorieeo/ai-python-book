"""A small fixed-window rate limiter on Django's cache API (needs add() and incr())."""
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    limit: int
    remaining: int
    retry_after: int  # seconds until the window ends (0 when the request is allowed)


class RateLimiter:
    def __init__(self, cache, *, prefix: str = "rl", clock=time.time):
        self.cache = cache
        self.prefix = prefix
        self.clock = clock  # injectable, so tests need not wait for real time

    def hit(
        self, scope: str, identity: str, *, limit: int, window: int, cost: int = 1
    ) -> RateLimitResult:
        """Count one request (or `cost` units); say whether it is within the limit."""
        now = int(self.clock())
        window_start = now - (now % window)
        key = f"{self.prefix}:{scope}:{identity}:{window_start}"
        self.cache.add(key, 0, timeout=window + 1)  # creates the counter if missing
        try:
            count = self.cache.incr(key, cost)  # atomic in Redis
        except ValueError:  # the key expired between add() and incr(): start fresh
            self.cache.add(key, cost, timeout=window + 1)
            count = cost
        allowed = count <= limit
        return RateLimitResult(
            allowed=allowed,
            limit=limit,
            remaining=max(0, limit - count),
            retry_after=0 if allowed else window - (now - window_start),
        )


def get_limiter() -> RateLimiter:
    # imported here so this module can be tested without Django
    from django.core.cache import cache

    return RateLimiter(cache)
