from lab.bugs.bug4_n_plus_one import FakeDB  # noqa: F401  (same fake database)


def last_message_per_conversation(db) -> dict[int, str]:
    conversations = db.conversations()
    messages = db.messages_for([c["id"] for c in conversations])      # one query for all of them
    last = {}
    for m in messages:
        last[m["conversation_id"]] = m["text"]
    return {c["id"]: last.get(c["id"], "") for c in conversations}
