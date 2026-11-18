"""Live dashboard WebSocket (Channels, Chapter 14). NOT executed in the book's test environment.

The server pushes {"type": "reading", "site_id", "sensor_id", "ts", "value"}. A member only ever receives readings from the
sites they may see: the check happens when they connect AND again for every message, because roles can change while connected."""
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from farmsense_core.permissions import can

from .models import Membership


class DashboardConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        user, self.farm_id = self.scope["user"], int(self.scope["url_route"]["kwargs"]["farm_id"])
        if not user.is_authenticated or await self._membership() is None:
            await self.close(code=4403)                                     # same answer for "no such farm" and "not yours"
            return
        self.group = f"farm.{self.farm_id}"
        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        if hasattr(self, "group"):
            await self.channel_layer.group_discard(self.group, self.channel_name)

    @database_sync_to_async
    def _membership(self):
        m = Membership.objects.filter(user=self.scope["user"], farm_id=self.farm_id).first()
        return m.to_core() if m else None

    async def reading_update(self, event):                                  # called for every group_send of type "reading.update"
        m = await self._membership()                                        # re-check: the person may have been demoted or removed
        if can(m, "dashboard.view", event["site_id"]):
            await self.send_json({"type": "reading", "site_id": event["site_id"], "sensor_id": event["sensor_id"],
                                  "ts": event["ts"], "value": event["value"]})
