"""Bug 4: the "your answer is ready" push never arrives, and no error is raised."""


class AnswerNotifier:
    def __init__(self, layer):
        self.layer = layer

    async def notify(self, conversation_id, text):
        self.layer.group_send(f"conv-{conversation_id}", {"type": "answer.ready", "text": text})   # no await
