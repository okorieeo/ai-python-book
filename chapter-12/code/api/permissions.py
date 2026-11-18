from rest_framework.permissions import BasePermission

class IsOwner(BasePermission):
    """Second line of defence: the queryset already hides other people's rows."""

    def has_object_permission(self, request, view, obj):
        return obj.user_id == request.user.id
