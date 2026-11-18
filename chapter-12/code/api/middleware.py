import re
import uuid

class RequestIdMiddleware:
    """Give every request an id, reuse it in logs and error bodies."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        supplied = request.headers.get("X-Request-ID", "")
        if re.fullmatch(r"[A-Za-z0-9_-]{8,64}", supplied):
            request.request_id = supplied
        else:
            request.request_id = f"req_{uuid.uuid4().hex[:12]}"
        response = self.get_response(request)
        response["X-Request-ID"] = request.request_id
        return response
