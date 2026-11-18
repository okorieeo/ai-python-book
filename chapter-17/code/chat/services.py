"""Business rules for chat (Chapter 11), extended in Chapter 17."""
from django.conf import settings
from django.db import transaction

from audit.services import Action, record
from core.security.ratelimit import get_limiter

from .models import Conversation


class DailyBudgetExceeded(Exception):
    def __init__(self, retry_after: int):
        super().__init__("The daily token budget is used up.")
        self.retry_after = retry_after


def delete_conversation(*, user, conversation: Conversation, request=None) -> None:
    """Delete a conversation and leave a trace of who deleted what. Both happen, or neither."""
    if conversation.user_id != user.id:
        raise Conversation.DoesNotExist  # services never trust the caller to have checked ownership
    with transaction.atomic():
        record(Action.CONVERSATION_DELETED, request=request, actor=user, target=conversation,
               metadata={"message_count": conversation.messages.count()})
        conversation.delete()


def check_daily_token_budget(*, user, estimated_tokens: int) -> None:
    """Cheap pre-check before calling the model. The UsageRecord ledger stays the source of truth for billing."""
    result = get_limiter().hit(
        "ai_tokens_day", str(user.pk), limit=settings.AI_DAILY_TOKEN_LIMIT, window=86_400, cost=estimated_tokens,
    )
    if not result.allowed:
        raise DailyBudgetExceeded(result.retry_after)
