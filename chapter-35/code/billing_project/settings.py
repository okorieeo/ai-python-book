"""A tiny project that exists only so the billing app can run and be tested on its own.

In your real project (Chapters 11 to 13) you add "billing" to INSTALLED_APPS and copy the
BILLING_* settings below into your settings module. AUTH_USER_MODEL stays yours.
"""
SECRET_KEY = "chapter-35-test-only-not-a-secret"
DEBUG = True
ALLOWED_HOSTS = ["testserver", "localhost"]
USE_TZ = True
TIME_ZONE = "UTC"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
ROOT_URLCONF = "billing_project.urls"

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.admin",
    "rest_framework",
    "billing",
]
MIDDLEWARE = [
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
    ]},
}]
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": "db.sqlite3"}}
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "EXCEPTION_HANDLER": "billing.permissions.billing_exception_handler",
}

# ---- Billing settings (copy these into your project) ----
BILLING_DEFAULT_CURRENCY = "USD"
BILLING_FREE_PLAN_CODE = "free"
BILLING_PAST_DUE_GRACE_DAYS = 7      # keep paid access this long after a failed renewal
BILLING_RENEWAL_GRACE_DAYS = 3       # tolerate a late "renewed" message from the provider
# Which model each kind of plan uses (model ids come from settings, Chapter 27).
BILLING_MODEL_STANDARD = "claude-haiku-5-5"
BILLING_MODEL_PREMIUM = "claude-sonnet-5-5"
