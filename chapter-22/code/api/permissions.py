def has_permission(name):
    """Build a permission class for ``permission_classes = [...]``."""

    class HasPermission(BasePermission):
        message = "You do not have access to this resource."

        def has_permission(self, request, view):
            return name in permissions_for(request.user)

    HasPermission.__name__ = f"Has_{name}"
    return HasPermission
