from rest_framework.permissions import SAFE_METHODS, BasePermission

from .models import FarmMember


class IsAdminRole(BasePermission):
    """Role 'admin'. The role is read from the database, not the token."""

    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == "admin"


class IsEmailVerified(BasePermission):
    message = "Verify your email address first."

    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.email_verified


class IsOwner(BasePermission):
    """Object-level: the row must belong to the caller (obj.user)."""

    def has_object_permission(self, request, view, obj):
        return obj.user_id == request.user.id


class HasFarmRole(BasePermission):
    """The view declares which roles may use each HTTP method."""

    def has_object_permission(self, request, view, farm):
        allowed = view.roles_for_method[request.method]
        return FarmMember.objects.filter(
            farm=farm, user=request.user, role__in=allowed
        ).exists()
