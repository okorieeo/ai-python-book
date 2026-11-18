# ======================== add to config/settings.py (Chapter 14) ========================

INSTALLED_APPS = [
    "daphne",                      # FIRST: makes `runserver` speak ASGI so WebSockets work in development
    # ... all the apps from Chapter 11 stay below ...
]

# Channel layer: how consumers (and Celery tasks, views) send messages to each other.
# Use a different Redis database number than the cache (/0 above, /1 here).
CHANNELS_REDIS_URL = env("CHANNELS_REDIS_URL", default="")
if CHANNELS_REDIS_URL:
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {"hosts": [CHANNELS_REDIS_URL]},
        }
    }
else:                              # development/tests only: works in ONE process, never in production
    CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}

# Which website origins may open WebSockets (the browser sends an Origin header)
WS_ALLOWED_ORIGINS = env.list("WS_ALLOWED_ORIGINS", default=["http://localhost:8000", "http://localhost:3000"])

# AI settings used by the chat consumer (real providers arrive in Chapter 29)
AI_PROVIDER = env("AI_PROVIDER", default="fake")
AI_GENERATION_TIMEOUT = env.float("AI_GENERATION_TIMEOUT", default=60.0)
FREE_MONTHLY_TOKEN_LIMIT = env.int("FREE_MONTHLY_TOKEN_LIMIT", default=100_000)   # replaced by plans in Chapter 35
