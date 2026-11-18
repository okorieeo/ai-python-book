from django.db import connection
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

@require_GET
@never_cache
def health(request):
    """Used by Docker/Dokploy to know the app and its database are alive."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        return JsonResponse({"status": "degraded", "database": "error"}, status=503)
    return JsonResponse({"status": "ok", "database": "ok"})
