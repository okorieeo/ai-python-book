"""Symptom: the conversation list takes 3 seconds with 500 conversations."""


class FakeDB:
    """Counts queries like Django's CaptureQueriesContext would."""

    def __init__(self, conversations: list[dict], messages: list[dict]):
        self._conversations, self._messages, self.queries = conversations, messages, []

    def conversations(self):
        self.queries.append("SELECT * FROM conversation")
        return list(self._conversations)

    def messages_for(self, conversation_ids: list[int]):
        self.queries.append(f"SELECT * FROM message WHERE conversation_id IN ({', '.join(map(str, conversation_ids))})")
        return [m for m in self._messages if m["conversation_id"] in conversation_ids]


def last_message_per_conversation(db: FakeDB) -> dict[int, str]:
    result = {}
    for conv in db.conversations():
        msgs = db.messages_for([conv["id"]])
        result[conv["id"]] = msgs[-1]["text"] if msgs else ""
    return result
