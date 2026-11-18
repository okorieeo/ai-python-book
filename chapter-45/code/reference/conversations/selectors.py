"""Read queries. Every function takes the user and scopes by it, so a forgotten filter is impossible."""
from django.db.models import Prefetch, QuerySet

from .models import Conversation, Message


def conversations_for(user) -> QuerySet[Conversation]:
    return Conversation.objects.filter(user=user, archived_at__isnull=True)


def conversation_list(user) -> QuerySet[Conversation]:
    """The list screen: one query for conversations plus one for each conversation's last message."""
    last = Message.objects.order_by("-created_at")
    return conversations_for(user).prefetch_related(Prefetch("messages", queryset=last[:1], to_attr="last_messages"))


def messages_for(user, conversation: Conversation) -> QuerySet[Message]:
    return Message.objects.filter(conversation=conversation, conversation__user=user, status__in=["ok", "pending"])
