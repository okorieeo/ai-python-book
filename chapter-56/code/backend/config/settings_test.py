"""Settings for the test suite: python manage.py test --settings=config.settings_test"""
import os

os.environ.setdefault("DJANGO_DEBUG", "1")

from .settings import *  # noqa: E402,F401,F403

AI_PROVIDER = "fake"
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]  # fast; tests only, never in production
CELERY_TASK_ALWAYS_EAGER = True
CHAT_CONTEXT_TOKEN_BUDGET = 400
CHAT_SUMMARY_KEEP_RECENT = 2
CHAT_MAX_MESSAGE_CHARS = 500
STRIPE_SECRET_KEY = "sk_test_dummy"
STRIPE_WEBHOOK_SECRET = "whsec_test_secret"
PAYSTACK_SECRET_KEY = "sk_test_paystack_secret"
REST_FRAMEWORK = {**REST_FRAMEWORK, "DEFAULT_THROTTLE_RATES": {"auth": "1000/min", "checkout": "1000/min"}}
