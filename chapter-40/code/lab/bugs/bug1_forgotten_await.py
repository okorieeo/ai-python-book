"""Symptom: the message is 'sent' but never appears in the store."""


async def save_message(store: list, text: str) -> None:
    store.append(text)


async def handle(store: list, text: str) -> int:
    save_message(store, text)
    return len(store)
