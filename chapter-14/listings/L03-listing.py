# in connect(): join a group named after the user
await self.channel_layer.group_add(f"user_{user.pk}", self.channel_name)

# anywhere (async code):
await channel_layer.group_send(f"user_{user_id}", {"type": "notify", "data": {...}})

# in the consumer: a method whose name matches the "type" ("notify") receives it
async def notify(self, event):
    await self.send_json(server_message("notification", event["data"]))
