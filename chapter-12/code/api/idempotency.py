import hashlib
import json
from functools import wraps

from rest_framework.exceptions import APIException, ValidationError
from rest_framework.response import Response

from chat.models import IdempotencyKey

class Conflict(APIException):
    status_code = 409
    default_code = "conflict"

def idempotent(view_method):
    """Replay the saved answer when a client retries with the same key."""

    @wraps(view_method)
    def wrapper(self, request, *args, **kwargs):
        key = request.headers.get("Idempotency-Key")
        if not key:
            return view_method(self, request, *args, **kwargs)
        if len(key) > 200:
            raise ValidationError({"Idempotency-Key": ["Too long."]})
        payload = json.dumps(request.data, sort_keys=True, default=str)
        digest = hashlib.sha256(f"{request.path}{payload}".encode()).hexdigest()

        record, created = IdempotencyKey.objects.get_or_create(
            user=request.user, key=key, defaults={"request_hash": digest}
        )
        if not created:                               # a retry
            if record.request_hash != digest:
                raise Conflict("This key was used for a different request.")
            if record.response_status is None:
                raise Conflict("The first request is still running.")
            return Response(record.response_body, status=record.response_status,
                            headers={"Idempotent-Replay": "true"})

        try:
            response = view_method(self, request, *args, **kwargs)
        except Exception:
            record.delete()                           # failed: allow a clean retry
            raise
        record.response_status = response.status_code
        record.response_body = response.data
        record.save(update_fields=["response_status", "response_body"])
        return response

    return wrapper
