from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from chat.models import Message

from .models import MessageFeedback
from .service import FeedbackError, FeedbackRecord, MessageNotFound, MessageRef, submit_feedback


class DjangoFeedbackStore:
    def get_message(self, message_id):
        row = (Message.objects.filter(pk=message_id)
               .values("pk", "conversation_id", "conversation__user_id", "role", "status").first())
        if row is None:
            return None
        return MessageRef(row["pk"], row["conversation_id"], row["conversation__user_id"], row["role"], row["status"])

    def upsert(self, rec: FeedbackRecord) -> bool:
        _, created = MessageFeedback.objects.update_or_create(
            user_id=rec.user_id, message_id=rec.message_id,
            defaults=dict(conversation_id=rec.conversation_id, rating=rec.rating, reason=rec.reason,
                          comment=rec.comment, may_use_for_improvement=rec.may_use_for_improvement))
        return created


class FeedbackThrottle(UserRateThrottle):
    rate = "60/min"


class MessageFeedbackView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [FeedbackThrottle]

    def put(self, request, message_id: int):
        data = request.data if isinstance(request.data, dict) else {}
        try:
            submit_feedback(DjangoFeedbackStore(), user_id=request.user.pk, message_id=message_id,
                            rating=data.get("rating"), reason=data.get("reason", ""), comment=data.get("comment", ""),
                            may_use_for_improvement=data.get("may_use_for_improvement") is True)
        except FeedbackError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except MessageNotFound:
            return Response({"detail": "Message not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)
