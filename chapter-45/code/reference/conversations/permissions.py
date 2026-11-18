from rest_framework.permissions import BasePermission

from core.rbac import can


class HasAction(BasePermission):
    """Deny by default: a view action with no entry in `required_actions` is refused."""

    def has_permission(self, request, view):
        action = getattr(view, "action", None)
        required = getattr(view, "required_actions", {}).get(action)
        if required is None:
            return False
        return can(getattr(request.user, "role", None), required)
