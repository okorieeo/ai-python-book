import asyncio


class FakeChannelLayer:
    """Stands in for Channels' channel layer: group_send is a coroutine, like the real one."""

    def __init__(self):
        self.delivered = []

    async def group_send(self, group, message):
        await asyncio.sleep(0)               # a real layer talks to Redis here
        self.delivered.append((group, message))
