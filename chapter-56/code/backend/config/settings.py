"""Settings for the AI Chat Assistant SaaS (Chapter 56).

Builds on the environment-based settings from Chapter 11 and the hardening from Chapter 17.
Only what this project adds is shown with comments; everything is driven by environment variables.
"""
import os
from datetime import timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def env(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if value is None:
        raise RuntimeError(f"Set {name} in the environment (see .env.example).")
    return value


def env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).lower() in {"1", "true", "yes", "on"}


DEBUG = env_bool("DJANGO_DEBUG", False)
# Fail closed (Chapter 17): without a real key the app refuses to start in production.
SECRET_KEY = env("DJANGO_SECRET_KEY", "dev-only-not-secret" if DEBUG else None)
ALLOWED_HOSTS = [h for h in env("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1" if DEBUG else "").split(",") if h]

INSTALLED_APPS = [
    "daphne",  # must come first so runserver speaks ASGI
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "channels",
    "rest_framework",
    "accounts",
    "chat",
    "billing",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]

ROOT_URLCONF = "config.urls"
ASGI_APPLICATION = "config.asgi.application"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
    ]},
}]

if os.environ.get("POSTGRES_DB"):
    DATABASES = {"default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("POSTGRES_DB"), "USER": env("POSTGRES_USER"), "PASSWORD": env("POSTGRES_PASSWORD"),
        "HOST": env("POSTGRES_HOST", "localhost"), "PORT": env("POSTGRES_PORT", "5432"),
    }}
else:  # local development and the tests in this chapter
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}}

AUTH_USER_MODEL = "accounts.User"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
TIME_ZONE = "UTC"
STATIC_URL = "static/"

# --- Redis: shared cache (tickets, rate limits) and the channel layer --------------------------
REDIS_URL = os.environ.get("REDIS_URL", "")
if REDIS_URL:
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.redis.RedisCache", "LOCATION": REDIS_URL}}
    CHANNEL_LAYERS = {"default": {"BACKEND": "channels_redis.core.RedisChannelLayer",
                                  "CONFIG": {"hosts": [REDIS_URL]}}}
else:  # one process only: fine for tests and a laptop, wrong for production (Chapter 17.8)
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
    CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}

# --- Celery (Chapter 15) --------------------------------------------------------------------------
CELERY_BROKER_URL = REDIS_URL or "memory://"
CELERY_TASK_ALWAYS_EAGER = env_bool("CELERY_TASK_ALWAYS_EAGER", not REDIS_URL)

# --- REST framework and JWT (Chapters 12 and 13) ---------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework_simplejwt.authentication.JWTAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],  # deny by default
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.ScopedRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {"auth": "20/min", "checkout": "10/min"},
}
SIMPLE_JWT = {"ACCESS_TOKEN_LIFETIME": timedelta(minutes=15), "REFRESH_TOKEN_LIFETIME": timedelta(days=14)}

# --- Chat -------------------------------------------------------------------------------------------
AI_PROVIDER = env("AI_PROVIDER", "fake")  # "fake" (tests, demos) or "anthropic"
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
AI_CHAT_MODEL = env("AI_CHAT_MODEL", "claude-sonnet-5-5")      # check the current names in the docs
AI_SUMMARY_MODEL = env("AI_SUMMARY_MODEL", "claude-haiku-5-5")  # cheaper model for memory summaries
AI_MAX_OUTPUT_TOKENS = int(env("AI_MAX_OUTPUT_TOKENS", "1024"))
CHAT_MAX_MESSAGE_CHARS = int(env("CHAT_MAX_MESSAGE_CHARS", "8000"))
CHAT_CONTEXT_TOKEN_BUDGET = int(env("CHAT_CONTEXT_TOKEN_BUDGET", "6000"))
CHAT_SUMMARY_KEEP_RECENT = int(env("CHAT_SUMMARY_KEEP_RECENT", "6"))
WS_TICKET_TTL_SECONDS = 60

# --- Billing -----------------------------------------------------------------------------------------
BILLING_GATEWAYS_ENABLED = [g for g in env("BILLING_GATEWAYS_ENABLED", "stripe,paystack").split(",") if g]
BILLING_PAST_DUE_GRACE_DAYS = 3
FRONTEND_URL = env("FRONTEND_URL", "http://localhost:3000")
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
PAYSTACK_SECRET_KEY = os.environ.get("PAYSTACK_SECRET_KEY", "")
PAYSTACK_CURRENCY = env("PAYSTACK_CURRENCY", "NGN")

LOGGING = {"version": 1, "disable_existing_loggers": False,
           "handlers": {"console": {"class": "logging.StreamHandler"}},
           "root": {"handlers": ["console"], "level": os.environ.get("LOG_LEVEL", "INFO")}}
