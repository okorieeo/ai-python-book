# ======================== add to chat/services.py (Chapter 14) ========================
from django.conf import settings

def monthly_token_limit(user) -> int:
    """Placeholder: one limit for everyone. Chapter 35 replaces this with the user's plan."""
    return settings.FREE_MONTHLY_TOKEN_LIMIT

def get_recent_history(conversation: Conversation, limit: int = 20) -> list[dict]:
    """The last `limit` messages, oldest first, as {"role", "content"} dictionaries for the AI model."""
    recent = list(conversation.messages.order_by("-created_at", "-id")[:limit])
    recent.reverse()
    return [{"role": m.role, "content": m.content} for m in recent]
