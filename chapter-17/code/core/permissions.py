from rest_framework.permissions import BasePermission


class IsOwner(BasePermission):
    """Object-level rule: the object must belong to the requesting user."""

    def has_object_permission(self, request, view, obj):
        return obj.user_id == request.user.id


class OwnedQuerysetMixin:
    """Every query starts from "the current user's rows".

    Other users' objects then simply do not exist for the caller. Put the mixin
    BEFORE the DRF base class:
    class ConversationViewSet(OwnedQuerysetMixin, viewsets.ModelViewSet)
    """

    owner_field = "user"

    def get_queryset(self):
        return super().get_queryset().filter(**{self.owner_field: self.request.user})
