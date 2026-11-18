from core.security.env import require_secret      # with the other imports

SECRET_KEY = require_secret("DJANGO_SECRET_KEY")   # replaces env("DJANGO_SECRET_KEY")
# old keys, kept only while rotating
SECRET_KEY_FALLBACKS = env.list("DJANGO_SECRET_KEY_FALLBACKS", default=[])

# ---------------------------------------------------------------- security (Chapter 17)
# set TRUSTED_PROXY_COUNT to 1 behind Traefik/Dokploy
TRUSTED_PROXY_COUNT = env.int("TRUSTED_PROXY_COUNT", default=0)
FIELD_ENCRYPTION_KEYS = env.list("FIELD_ENCRYPTION_KEYS", default=[])
# a simple guard until Chapter 35 adds plans
AI_DAILY_TOKEN_LIMIT = env.int("AI_DAILY_TOKEN_LIMIT", default=50_000)
ADMIN_URL = env("DJANGO_ADMIN_URL", default="admin/")

X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
