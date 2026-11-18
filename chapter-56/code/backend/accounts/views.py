import secrets

from django.conf import settings
from django.core.cache import cache
from rest_framework import generics, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .serializers import MeSerializer, RegisterSerializer

TICKET_PREFIX = "wsticket:"


class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]  # public on purpose (Chapter 17.3)
    throttle_scope = "auth"


class LoginView(TokenObtainPairView):
    throttle_scope = "auth"


class RefreshView(TokenRefreshView):
    throttle_scope = "auth"


class MeView(generics.RetrieveUpdateAPIView):
    serializer_class = MeSerializer

    def get_object(self):
        return self.request.user


class WebSocketTicketView(APIView):
    """Swap a normal login for a 60-second, single-use ticket to open the chat socket.

    Browsers cannot set an Authorization header on a WebSocket, and a long-lived JWT in the URL would
    end up in proxy logs and browser history. A ticket that dies after one use makes that harmless.
    """

    def post(self, request):
        ticket = secrets.token_urlsafe(32)
        cache.set(TICKET_PREFIX + ticket, request.user.pk, timeout=settings.WS_TICKET_TTL_SECONDS)
        return Response({"ticket": ticket, "expires_in": settings.WS_TICKET_TTL_SECONDS},
                        status=status.HTTP_201_CREATED)


def redeem_ticket(ticket: str) -> int | None:
    """Return the user id for a valid ticket and burn it. Safe to call from sync code only."""
    if not ticket:
        return None
    key = TICKET_PREFIX + ticket
    user_id = cache.get(key)
    # delete() returns True only for the caller that actually removed the key, so two sockets racing
    # with the same ticket cannot both win.
    if user_id is not None and cache.delete(key):
        return user_id
    return None
