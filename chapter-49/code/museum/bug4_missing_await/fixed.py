class AnswerNotifier:
    def __init__(self, layer):
        self.layer = layer

    async def notify(self, conversation_id, text):
        await self.layer.group_send(f"conv-{conversation_id}", {"type": "answer.ready", "text": text})
