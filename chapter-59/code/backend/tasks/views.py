from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from core.api_fields import UserZoneMixin
from core.permissions import IsOwner, OwnedQuerysetMixin
from core.security.sanitize import build_filters
from core.throttles import BurstThrottle

from . import services
from .models import Task
from .serializers import TaskSerializer


class TaskViewSet(UserZoneMixin, OwnedQuerysetMixin, viewsets.ModelViewSet):
    queryset = Task.objects.all()
    serializer_class = TaskSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwner]
    throttle_classes = [BurstThrottle]
    lookup_field = "public_id"

    def get_queryset(self):
        qs = super().get_queryset()
        # Only these filters exist; anything else in the query string is ignored
        # (Chapter 17).
        return qs.filter(**build_filters(self.request.query_params, {"status": "status", "priority": "priority"}))

    def perform_create(self, serializer):
        serializer.instance = services.create_task(user=self.request.user, **serializer.validated_data)

    def perform_update(self, serializer):
        serializer.instance = services.update_task(user=self.request.user, task=serializer.instance, **serializer.validated_data)

    def perform_destroy(self, instance):
        services.delete_task(user=self.request.user, task=instance, request=self.request)

    @action(detail=True, methods=["post"])
    def complete(self, request, public_id=None):
        task = services.complete_task(user=request.user, task=self.get_object())
        return Response(self.get_serializer(task).data, status=status.HTTP_200_OK)
