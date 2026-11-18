from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from chat.models import Conversation

from . import services
from .models import SharedLink
from .serializers import (
    ShareLinkCreatedSerializer,
    ShareLinkCreateSerializer,
    ShareLinkSerializer,
    SharedConversationSerializer,
)
from .throttles import PublicReadThrottle, ShareCreateThrottle

NOT_FOUND = {"code": "not_found", "message": "This link does not exist or is no longer active."}


def owned_conversation(request, conversation_id) -> Conversation:
    """404 for other people's conversations, exactly as for missing ones (AC-7)."""
    return get_object_or_404(Conversation, public_id=conversation_id, user=request.user)


class ShareLinkListCreateView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [ShareCreateThrottle]

    def get(self, request, conversation_id):  # listShareLinks
        conversation = owned_conversation(request, conversation_id)
        links = services.list_share_links(user=request.user, conversation=conversation)
        return Response(ShareLinkSerializer(links, many=True).data)

    def post(self, request, conversation_id):  # createShareLink
        conversation = owned_conversation(request, conversation_id)
        body = ShareLinkCreateSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        link, url = services.create_share_link(
            user=request.user, conversation=conversation,
            expires_in=body.validated_data["expires_in"], request=request,
        )
        link.url = url  # a plain attribute, not a database field: it is shown once and never stored
        return Response(ShareLinkCreatedSerializer(link).data, status=status.HTTP_201_CREATED)


class ShareLinkDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, conversation_id, link_id):  # revokeShareLink
        conversation = owned_conversation(request, conversation_id)
        link = get_object_or_404(SharedLink, public_id=link_id, conversation=conversation, created_by=request.user)
        services.revoke_share_link(user=request.user, link=link, request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class PublicSharedConversationView(APIView):
    """No sign-in, no cookies, no session: the token in the path is the only credential."""

    authentication_classes: list = []
    permission_classes = [AllowAny]
    throttle_classes = [PublicReadThrottle]

    def get(self, request, token):  # getSharedConversation
        try:
            link = services.resolve_public_link(token)
        except services.LinkNotFound:
            response = Response(NOT_FOUND, status=status.HTTP_404_NOT_FOUND)  # identical for every failure (AC-6)
        else:
            services.record_view(link)
            payload = {
                "title": link.conversation.title,
                "shared_at": link.created_at,
                "messages": services.snapshot_messages(link),
            }
            response = Response(SharedConversationSerializer(payload).data)
        response["Cache-Control"] = "no-store"        # AC-10
        response["X-Robots-Tag"] = "noindex, nofollow"  # AC-10
        return response
