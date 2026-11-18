"""One JSON log line per request: method, normalised path, status, duration, user id.

Fits Chapter 17's JsonFormatter (the `event` and `fields` extras) and the request id
filter. No query strings (they can carry tokens), no bodies, no headers. Paths are
normalised: /api/conversations/42/ and one with a UUID both become
/api/conversations/:id/, so your logs stay searchable. Needs no Django imports.
"""
from __future__ import annotations

import logging
import re
import time

_HEX = "[0-9a-fA-F]"
_UUID = re.compile(rf"/{_HEX}{{8}}-{_HEX}{{4}}-{_HEX}{{4}}-{_HEX}{{4}}-{_HEX}{{12}}(?=/|$)")
_NUMBER = re.compile(r"/\d+(?=/|$)")
_OPAQUE = re.compile(r"/[A-Za-z0-9_\-]{20,}(?=/|$)")
SKIP_PATHS = frozenset({"/healthz/", "/readyz/"})


def normalize_path(path: str) -> str:
    path = path.split("?", 1)[0]
    path = _UUID.sub("/:id", path)
    path = _NUMBER.sub("/:id", path)
    return _OPAQUE.sub("/:token", path)


def _level_for(status: int) -> int:
    return logging.ERROR if status >= 500 else logging.INFO


class RequestLogMiddleware:
    """Add it to MIDDLEWARE, after the request id middleware (see Chapter 55)."""

    def __init__(self, get_response, logger: logging.Logger | None = None,
                 clock=time.perf_counter):
        self.get_response = get_response
        self.logger = logger or logging.getLogger("http")
        self.clock = clock

    def _user_id(self, request):
        user = getattr(request, "user", None)
        if user is not None and getattr(user, "is_authenticated", False):
            return str(getattr(user, "pk", "") or "") or None
        return None

    def _log(self, request, status: int, started: float) -> None:
        if request.path in SKIP_PATHS:
            return
        fields = {
            "method": request.method,
            "path": normalize_path(request.path),
            "status": status,
            "ms": int((self.clock() - started) * 1000),
            "user_id": self._user_id(request),
        }
        self.logger.log(_level_for(status), "request",
                        extra={"event": "http_request", "fields": fields})

    def __call__(self, request):
        started = self.clock()
        try:
            response = self.get_response(request)
        except Exception:
            self._log(request, 500, started)
            raise
        self._log(request, response.status_code, started)
        return response
