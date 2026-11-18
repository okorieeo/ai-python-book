from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .models import Conversation
from .serializers import MessageCreateSerializer, MessageSerializer


class MessageCreateView(APIView):
    """POST /conversations/<public_id>/messages/  with {"client_id": "<uuid>", "content": "..."}

    201 = stored now. 200 = this client_id was stored earlier (a retry); the same message is returned.
    409 = the client_id was used before with different content.
    Add your Chapter 17 throttle classes here (throttle_classes = [...]).
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, conversation_id):
        # Owner-scoped lookup (Chapter 17, section 17.3): someone else's conversation is a 404, not a 403.
        conversation = get_object_or_404(Conversation, public_id=conversation_id, user=request.user)
        data = MessageCreateSerializer(data=request.data)
        data.is_valid(raise_exception=True)

        try:
            message, created = services.create_user_message(
                user=request.user,
                conversation=conversation,
                content=data.validated_data["content"],
                client_id=data.validated_data.get("client_id"),
            )
        except services.ClientIdReused:
            return Response({"detail": "This client_id was already used for a different message."}, status=status.HTTP_409_CONFLICT)

        return Response(MessageSerializer(message).data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)
