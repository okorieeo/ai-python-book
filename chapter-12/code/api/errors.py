from django.http import JsonResponse
from rest_framework.views import exception_handler

CODES = {
    400: "validation_error", 401: "not_authenticated", 402: "quota_exceeded",
    403: "permission_denied", 404: "not_found", 405: "method_not_allowed",
    409: "conflict", 429: "rate_limited", 503: "provider_unavailable",
}

def api_exception_handler(exc, context):
    response = exception_handler(exc, context)    # DRF's normal handling first
    if response is None:                           # not an API error: a 500
        return None
    code = CODES.get(response.status_code, "error")
    if getattr(exc, "get_codes", None) and exc.get_codes() == "no_active_account":
        code = "invalid_credentials"               # never say which part was wrong
    data = response.data
    if response.status_code == 400 and isinstance(data, dict):
        body = {"code": code, "message": "Some fields are invalid.", "fields": data}
    else:
        detail = data.get("detail") if isinstance(data, dict) else None
        body = {"code": code, "message": str(detail or "Request failed.")}
    body["request_id"] = getattr(context["request"], "request_id", None)
    response.data = {"error": body}
    return response

def _json_error(request, status, code, message):
    body = {"code": code, "message": message,
            "request_id": getattr(request, "request_id", None)}
    return JsonResponse({"error": body}, status=status)

def not_found(request, exception=None):          # Django's handler404
    return _json_error(request, 404, "not_found", "Unknown path.")

def server_error(request):                        # Django's handler500
    return _json_error(request, 500, "server_error", "Something went wrong.")
