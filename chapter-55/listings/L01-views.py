import logging
 
import redis as redis_lib
from django.conf import settings
from django.db import connection
from django.http import JsonResponse
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
 
from core.observability.readiness import (
    database_check, detail_payload, overall_ok, public_payload, redis_check, run_checks,
)
 
logger = logging.getLogger("readiness")
_redis = redis_lib.Redis.from_url(
    settings.REDIS_URL, socket_connect_timeout=1, socket_timeout=1
)
 
 
@api_view(["GET"])
@permission_classes([AllowAny])  # public on purpose: the outside monitor has no login
@throttle_classes([])
def readyz(request):
    results = run_checks({
        "database": database_check(connection, close_after=True),  # see the note below
        "redis": redis_check(_redis),
    })
    ok = overall_ok(results)
    if not ok:  # the details go to YOUR logs, never to the caller
        logger.error("not ready", extra={
            "event": "readiness_failed",
            "fields": detail_payload(results)["checks"],
        })
    return JsonResponse(public_payload(results), status=200 if ok else 503)
