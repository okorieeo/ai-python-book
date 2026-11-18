"""A small, framework-free AI service layer: rate limit, cache, retry, fallback."""
from __future__ import annotations

import hashlib
import random
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Callable

class ProviderError(Exception):
    """The AI provider failed (timeout, 5xx, overloaded...). Worth retrying."""

class RateLimitExceeded(Exception):
    """The user sent too many requests in the time window."""

# ---------------------------------------------------------------- cache
class TTLCache:
    """Key/value cache whose entries expire after ttl seconds (cache-aside pattern)."""

    def __init__(self, ttl: float = 300, clock: Callable[[], float] = time.monotonic) -> None:
        self.ttl = ttl
        self.clock = clock
        self._data: dict[str, tuple[float, str]] = {}

    def get(self, key: str) -> str | None:
        item = self._data.get(key)
        if item is None:
            return None
        expires_at, value = item
        if self.clock() >= expires_at:
            del self._data[key]          # expired
            return None
        return value

    def set(self, key: str, value: str) -> None:
        self._data[key] = (self.clock() + self.ttl, value)

# ---------------------------------------------------------------- rate limiter
class RateLimiter:
    """Allow at most `limit` calls per user within `window` seconds (sliding window)."""

    def __init__(self, limit: int = 5, window: float = 60, clock: Callable[[], float] = time.monotonic) -> None:
        self.limit = limit
        self.window = window
        self.clock = clock
        self._calls: dict[int, deque[float]] = defaultdict(deque)

    def check(self, user_id: int) -> None:
        now = self.clock()
        calls = self._calls[user_id]
        while calls and now - calls[0] >= self.window:
            calls.popleft()               # forget calls outside the window
        if len(calls) >= self.limit:
            raise RateLimitExceeded(f"Limit of {self.limit} requests per {self.window:.0f}s reached")
        calls.append(now)

# ---------------------------------------------------------------- retry
def retry_with_backoff(
    func: Callable[[], str],
    attempts: int = 3,
    base_delay: float = 0.5,
    max_delay: float = 8.0,
    sleep: Callable[[float], None] = time.sleep,
) -> str:
    """Call func; on ProviderError wait (exponential backoff + jitter) and try again."""
    for attempt in range(1, attempts + 1):
        try:
            return func()
        except ProviderError:
            if attempt == attempts:
                raise                      # out of attempts: let the caller decide
            ceiling = min(max_delay, base_delay * 2 ** (attempt - 1))
            sleep(random.uniform(0, ceiling))   # "full jitter" avoids thundering herds
    raise AssertionError("unreachable")

# ---------------------------------------------------------------- service
@dataclass
class AIResult:
    text: str
    source: str        # "cache", "primary" or "fallback"

class AIService:
    """The single place in the app that talks to AI models."""

    def __init__(
        self,
        primary: Callable[[str], str],
        fallback: Callable[[str], str] | None = None,
        cache: TTLCache | None = None,
        limiter: RateLimiter | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.primary = primary
        self.fallback = fallback
        self.cache = cache
        self.limiter = limiter
        self.sleep = sleep

    @staticmethod
    def _key(prompt: str) -> str:
        return hashlib.sha256(prompt.strip().lower().encode("utf-8")).hexdigest()

    def ask(self, user_id: int, prompt: str) -> AIResult:
        if self.limiter:
            self.limiter.check(user_id)                      # 1. protect cost and fairness

        key = self._key(prompt)
        if self.cache:
            cached = self.cache.get(key)                     # 2. cheap path first
            if cached is not None:
                return AIResult(cached, "cache")

        try:
            text = retry_with_backoff(lambda: self.primary(prompt), sleep=self.sleep)   # 3. main model
            source = "primary"
        except ProviderError:
            if self.fallback is None:
                raise
            text = self.fallback(prompt)                     # 4. degrade gracefully
            source = "fallback"

        if self.cache and source == "primary":
            self.cache.set(key, text)                        # only cache good answers
        return AIResult(text, source)
