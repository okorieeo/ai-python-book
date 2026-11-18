import logging
import re
import time
import uuid

from .request_context import request_id_var

logger = logging.getLogger("request")
VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")

class RequestIDMiddleware:
    """Give every request an id, expose it in the response, and log one line per request."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        incoming = request.headers.get("X-Request-ID", "")
        request_id = incoming if VALID_REQUEST_ID.match(incoming) else "req_" + uuid.uuid4().hex[:12]
        request.request_id = request_id
        token = request_id_var.set(request_id)
        started = time.monotonic()
        try:
            response = self.get_response(request)
            duration_ms = (time.monotonic() - started) * 1000
            logger.info("%s %s -> %s (%.0f ms)", request.method, request.path, response.status_code, duration_ms)
            response["X-Request-ID"] = request_id
            return response
        finally:
            request_id_var.reset(token)
