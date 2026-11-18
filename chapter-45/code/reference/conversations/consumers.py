import logging

from channels.generic.websocket import AsyncJsonWebsocketConsumer

logger = logging.getLogger("chat.ws")


class ChatConsumer(AsyncJsonWebsocketConsumer):
    """Live updates for ONE conversation. Authenticated, owner-checked, and it never sends other users' data."""

    async def connect(self):
        user = self.scope.get("user")
        if user is None or not user.is_authenticated:
            await self.close(code=4401)                              # app-defined: not authenticated
            return
        self.public_id = self.scope["url_route"]["kwargs"]["public_id"]
        if not await self._owns(user, self.public_id):
            await self.close(code=4404)                              # same answer for missing and not yours
            return
        self.group = f"conversation.{self.public_id}"
        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()
        logger.info("ws connect", extra={"event": "ws_connect", "fields": {"channel": self.channel_name}})

    async def disconnect(self, code):
        if hasattr(self, "group"):
            await self.channel_layer.group_discard(self.group, self.channel_name)

    async def message_created(self, event):                          # handler name = event type "message.created"
        await self.send_json({"type": "message.created", "message": event["message"]})

    async def _owns(self, user, public_id) -> bool:
        from channels.db import database_sync_to_async
        from .models import Conversation
        return await database_sync_to_async(Conversation.objects.filter(user=user, public_id=public_id).exists)()
