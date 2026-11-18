"""Send a live message to a user from ordinary (synchronous) code: views, Celery tasks, webhook handlers."""
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

def notify_user(user_id: int, *, kind: str, title: str, body: str = "") -> None:
    """Delivered to every open connection of that user; silently does nothing if they are offline."""
    layer = get_channel_layer()
    async_to_sync(layer.group_send)(
        f"user_{user_id}",
        {"type": "notify", "data": {"kind": kind, "title": title, "body": body}},   # "notify" -> ChatConsumer.notify
    )
