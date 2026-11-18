import logging

from channels.generic.websocket import AsyncJsonWebsocketConsumer

logger = logging.getLogger("chat.ws")

class LoggedConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        logger.info("ws connect", extra={"event": "ws_connect", "fields": {
            "channel": self.channel_name, "user": getattr(user, "public_id", None) and str(user.public_id),
            "origin": dict(self.scope["headers"]).get(b"origin", b"").decode()}})
        await super().connect()

    async def receive_json(self, content, **kwargs):
        logger.debug("ws receive", extra={"event": "ws_receive", "fields": {
            "channel": self.channel_name, "type": content.get("type")}})       # the event type, not the text
        await super().receive_json(content, **kwargs)

    async def disconnect(self, code):
        logger.info("ws disconnect", extra={"event": "ws_disconnect", "fields": {"channel": self.channel_name, "code": code}})
        await super().disconnect(code)
