from resilient_ai import AIService, ProviderError, RateLimiter, RateLimitExceeded, TTLCache

calls = {"primary": 0}

def flaky_primary(prompt: str) -> str:
    """Fails twice, then works: simulates an overloaded provider."""
    calls["primary"] += 1
    if calls["primary"] <= 2:
        raise ProviderError("503 overloaded")
    return f"[primary] answer to: {prompt}"

def always_down(prompt: str) -> str:
    raise ProviderError("provider is down")

def small_model(prompt: str) -> str:
    return f"[fallback] short answer to: {prompt}"

waits: list[float] = []                       # record sleeps instead of really waiting

service = AIService(
    primary=flaky_primary,
    fallback=small_model,
    cache=TTLCache(ttl=300),
    limiter=RateLimiter(limit=3, window=60),
    sleep=waits.append,
)

print(service.ask(1, "What is Docker?"))      # retries twice, then succeeds
print(service.ask(1, "what is docker?  "))    # served from the cache
print("primary was called", calls["primary"], "times; waited", len(waits), "times")

outage = AIService(primary=always_down, fallback=small_model, sleep=lambda s: None)
print(outage.ask(2, "Explain Celery"))        # falls back to the small model

try:
    for i in range(5):
        service.ask(3, f"question {i}")
except RateLimitExceeded as error:
    print("Blocked:", error)
