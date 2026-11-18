import uuid

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404
from rest_framework import exceptions, status
from rest_framework.views import exception_handler
from rest_framework_simplejwt.exceptions import InvalidToken


class InvalidLink(exceptions.APIException):
    """A verification or reset link that is wrong, expired or already used."""

    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "invalid_token"
    default_detail = "This link is invalid or has expired."


def api_exception_handler(exc, context):
    """Turn every DRF error into the error format designed in Chapter 8."""
    if isinstance(
        exc, Http404
    ):  # Django's own exceptions, as DRF treats them
        exc = exceptions.NotFound()
    elif isinstance(exc, DjangoPermissionDenied):
        exc = exceptions.PermissionDenied()
    response = exception_handler(exc, context)
    if response is None:
        return None  # a real bug: let Django return 500 and log it
    details = None
    if isinstance(exc, exceptions.ValidationError):
        code, response.status_code = "validation_error", 422
        message, details = (
            "The request contains invalid fields.",
            response.data,
        )
    elif isinstance(exc, InvalidToken):
        expired = "expired" in str(exc.detail).lower()
        code = "token_expired" if expired else "not_authenticated"
        message = (
            "The token is expired." if expired else "The token is not valid."
        )
    elif isinstance(
        exc, exceptions.AuthenticationFailed | exceptions.NotAuthenticated
    ):
        code, message = "not_authenticated", "Missing or invalid credentials."
    elif isinstance(exc, exceptions.PermissionDenied):
        code, message = "permission_denied", "You do not have permission."
    elif isinstance(exc, exceptions.NotFound):
        code, message = "not_found", "Not found."
    elif isinstance(exc, exceptions.Throttled):
        code, message = "rate_limited", "Too many requests. Try again later."
    else:
        code, message = exc.default_code, str(exc.detail)
    if code in ("not_authenticated", "token_expired"):
        response.status_code = (
            401  # DRF would send 403 when no auth class replies
        )
        response["WWW-Authenticate"] = "Bearer"
    error = {
        "code": code,
        "message": message,
        "request_id": "req_" + uuid.uuid4().hex[:6],
    }
    if details:
        error["details"] = details
    response.data = {"error": error}
    return response
