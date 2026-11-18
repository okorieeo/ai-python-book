"""Gating in the API: refuse a request when the user's plan does not include the feature."""

from __future__ import annotations

from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission

from .entitlements import has_feature
from .usage import LimitExceeded


class FeatureNotInPlan(PermissionDenied):
    default_code = "feature_not_in_plan"
    default_detail = "Your plan does not include this feature."


def billing_exception_handler(exc, context):
    """Turns LimitExceeded into a clear 403 with real numbers.

    Do not put numbers inside an APIException's detail: DRF converts every value in it to text,
    and your frontend would receive "30" instead of 30. Plug this into your Chapter 8 handler by
    calling it first:  response = billing_exception_handler(exc, context)  and returning it if not None.
    """
    from rest_framework.response import Response
    from rest_framework.views import exception_handler

    if isinstance(exc, LimitExceeded):
        # 403 keeps proxies and clients simple. Some APIs use 402 here; pick one and stay consistent.
        return Response(
            {
                "detail": "You have reached your plan's limit.",
                "code": "limit_reached",
                "key": exc.key,
                "limit": exc.limit,
                "used": exc.used,
            },
            status=status.HTTP_403_FORBIDDEN,
        )
    return exception_handler(exc, context)


def entitlement_required(key: str):
    """A DRF permission class: `permission_classes = [IsAuthenticated, entitlement_required("ai.agent_tools")]`."""

    class RequiresEntitlement(BasePermission):
        def has_permission(self, request, view) -> bool:
            if not (request.user and request.user.is_authenticated):
                return False
            if not has_feature(request.user, key):
                raise FeatureNotInPlan(code="feature_not_in_plan")
            return True

    RequiresEntitlement.__name__ = f"Requires_{key.replace('.', '_')}"
    return RequiresEntitlement
