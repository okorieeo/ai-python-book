"""Business rules for chat. Views, WebSocket consumers and Celery tasks all call these functions."""
from datetime import datetime

from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone

from .models import Conversation, Message, UsageRecord

MAX_TITLE_LENGTH = 200

def create_conversation(*, user, title: str = "") -> Conversation:
    title = title.strip() or "New conversation"
    if len(title) > MAX_TITLE_LENGTH:
        raise ValueError(f"The title may not be longer than {MAX_TITLE_LENGTH} characters.")
    return Conversation.objects.create(user=user, title=title)

def get_conversation_for_user(*, user, public_id) -> Conversation:
    """Always scope by owner. Raises Conversation.DoesNotExist (the API turns this into a 404)."""
    return Conversation.objects.get(user=user, public_id=public_id)

def add_user_message(*, conversation: Conversation, content: str) -> Message:
    content = content.strip()
    if not content:
        raise ValueError("A message cannot be empty.")
    with transaction.atomic():
        message = Message.objects.create(conversation=conversation, role=Message.Role.USER, content=content)
        conversation.save(update_fields=["updated_at"])          # bump "last activity"
    return message

def save_assistant_reply(*, conversation: Conversation, text: str, input_tokens: int, output_tokens: int,
                         model_name: str) -> Message:
    """Store the answer and bill the tokens together, or neither."""
    with transaction.atomic():
        message = Message.objects.create(
            conversation=conversation, role=Message.Role.ASSISTANT, content=text,
            model_name=model_name, input_tokens=input_tokens, output_tokens=output_tokens,
        )
        UsageRecord.objects.create(
            user=conversation.user, message=message, input_tokens=input_tokens, output_tokens=output_tokens,
        )
        conversation.save(update_fields=["updated_at"])
    return message

def tokens_used_this_month(*, user, now: datetime | None = None) -> int:
    now = now or timezone.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    total = UsageRecord.objects.filter(user=user, created_at__gte=month_start).aggregate(
        total=Sum(F("input_tokens") + F("output_tokens"))
    )["total"]
    return total or 0
