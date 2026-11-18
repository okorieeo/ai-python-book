"""Health endpoints from Chapter 54, plus a check that the task queue (Redis) is reachable.
The logic lives in health_checks.py (copy it from Chapter 54's code)."""
from django.core.cache import cache
from django.db import connection
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from .health_checks import liveness, readiness


def _database():
    with connection.cursor() as cur:
        cur.execute("SELECT 1")


def _redis():
    cache.set("health:ping", "1", 5)
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
