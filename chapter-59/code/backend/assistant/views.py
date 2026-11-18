import re

from django.http import Http404
from rest_framework import permissions, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from chat.services import DailyBudgetExceeded
from core.throttles import BurstThrottle

from . import services
from .agent import ModelUnavailable
from .models import PendingAction, PushDevice
from .prompt import MAX_USER_MESSAGE_CHARS


class AssistantBurstThrottle(BurstThrottle):
    scope = "assistant_burst"
    # eight requests a minute is generous for a person typing, and slow for a script
    limit = 8
    window = 60


class MessageSerializer(serializers.Serializer):
    text = serializers.CharField(max_length=MAX_USER_MESSAGE_CHARS, trim_whitespace=True)


class DecisionSerializer(serializers.Serializer):
    approve = serializers.BooleanField()


def problem(detail: str, code: str, http_status: int, **headers) -> Response:
    return Response({"detail": detail, "code": code}, status=http_status, headers=headers)


def outcome_json(outcome: services.Outcome) -> dict:
    return {"status": outcome.status, "text": outcome.text, "pending": outcome.pending}


class MessageView(APIView):
    """POST /api/v1/assistant/messages/  {"text": "..."}  (the non-streaming way in; the
    WebSocket is the other)"""

    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [AssistantBurstThrottle]

    def post(self, request):
        serializer = MessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            outcome = services.send_message(user=request.user, text=serializer.validated_data["text"], request=request)
        except services.AssistantBusy:
            return problem("Answer the open question first.", "awaiting_confirmation", status.HTTP_409_CONFLICT)
        except DailyBudgetExceeded as exc:
            return problem("Today's assistant allowance is used up.", "daily_budget", status.HTTP_429_TOO_MANY_REQUESTS,
                           **{"Retry-After": str(exc.retry_after)})
        except ModelUnavailable:
            return problem("The assistant is unavailable right now. Try again in a minute.", "model_unavailable", status.HTTP_503_SERVICE_UNAVAILABLE)
        except ValueError as exc:  # empty after cleaning
            return problem(str(exc), "invalid_message", status.HTTP_400_BAD_REQUEST)
        return Response(outcome_json(outcome))


class DecisionView(APIView):
    """POST /api/v1/assistant/actions/<action_id>/  {"approve": true}"""

    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [AssistantBurstThrottle]

    def post(self, request, action_id):
        serializer = DecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            outcome = services.decide(user=request.user, action_id=action_id, approve=serializer.validated_data["approve"], request=request)
        except PendingAction.DoesNotExist:
            raise Http404
        except services.ActionNotPending:
            return problem("That question was already answered or has expired.", "not_pending", status.HTTP_409_CONFLICT)
        except ModelUnavailable:
            return problem("The assistant is unavailable right now. Your answer was saved.", "model_unavailable", status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response(outcome_json(outcome))


class NewChatView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        services.archive_thread(request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class PushDeviceView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        token = str(request.data.get("token", ""))
        if not re.fullmatch(r"(Exponent|Expo)PushToken\[[A-Za-z0-9_-]{10,100}\]", token):
            return problem("Not an Expo push token.", "invalid_token", status.HTTP_400_BAD_REQUEST)
        PushDevice.objects.update_or_create(token=token, defaults={"user": request.user})  # a phone changes owner on re-login
        return Response(status=status.HTTP_204_NO_CONTENT)
