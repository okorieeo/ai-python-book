"""Django wrapper for health_checks.py.   NOT executed in this book's test environment (Django was not installed there).

urls.py:
    path("health/live", health_views.live),
    path("health/ready", health_views.ready),

Trailing-slash note: the compose healthcheck calls /health/live without a slash, so keep APPEND_SLASH from redirecting it,
or register the path exactly as written.
"""
from django.core.cache import cache
from django.db import connection
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from .health_checks import liveness, readiness


def _database():
    with connection.cursor() as cur:
        cur.execute("SELECT 1")


def _redis():
    cache.set("health:ping", "1", 5)   # uses the Redis-backed cache from Chapter 17.8; swap in a direct client if you prefer
    if cache.get("health:ping") != "1":
        raise RuntimeError("redis round trip failed")


@require_GET
def live(request):
    status, body = liveness()
    return JsonResponse(body, status=status)


@require_GET
def ready(request):
    status, body = readiness({"database": _database, "redis": _redis})
    return JsonResponse(body, status=status)
