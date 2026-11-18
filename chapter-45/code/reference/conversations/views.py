from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from core.chat.service import ChatError

from . import selectors, services
from .permissions import HasAction
from .serializers import ConversationSerializer, MessageSerializer, SendMessageSerializer


class ConversationViewSet(mixins.CreateModelMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                          mixins.DestroyModelMixin, viewsets.GenericViewSet):
    """Conversations belong to one user. Another user's conversation is a 404, never a 403."""

    serializer_class = ConversationSerializer
    permission_classes = [IsAuthenticated, HasAction]
    lookup_field = "public_id"
    required_actions = {"list": "conversation.read", "retrieve": "conversation.read", "create": "conversation.create",
                        "destroy": "conversation.delete", "messages": "conversation.read", "send": "message.send"}

    def get_queryset(self):
        return selectors.conversation_list(self.request.user)          # scoped to request.user

    def perform_create(self, serializer):
        serializer.instance = services.create_conversation(user=self.request.user, title=serializer.validated_data.get("title", ""))

    def perform_destroy(self, instance):
        services.archive_conversation(user=self.request.user, conversation=instance)     # archive, do not hard-delete

    @extend_schema(responses=MessageSerializer(many=True))
    @action(detail=True, methods=["get"])
    def messages(self, request, public_id=None):
        conversation = self.get_object()
        page = self.paginate_queryset(selectors.messages_for(request.user, conversation))
        return self.get_paginated_response(MessageSerializer(page, many=True).data)

    @extend_schema(request=SendMessageSerializer, responses={201: MessageSerializer},
                   parameters=[OpenApiParameter("Idempotency-Key", str, OpenApiParameter.HEADER, required=True)])
    @action(detail=True, methods=["post"], throttle_classes=[ScopedRateThrottle], throttle_scope="chat_send")
    def send(self, request, public_id=None):
        conversation = self.get_object()
        data = SendMessageSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        service = services.build_chat_service()
        try:
            result = service.send(user_id=request.user.pk, conversation_id=str(conversation.public_id),
                                  text=data.validated_data["content"], idempotency_key=request.headers.get("Idempotency-Key", ""))
        except ChatError as exc:
            return Response({"detail": str(exc)}, status=exc.status)
        from .models import Message
        reply = Message.objects.get(pk=result.assistant_message.id)
        return Response(MessageSerializer(reply).data, status=status.HTTP_200_OK if result.deduplicated else status.HTTP_201_CREATED)
