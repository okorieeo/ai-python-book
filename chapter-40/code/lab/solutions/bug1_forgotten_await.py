async def save_message(store: list, text: str) -> None:
    store.append(text)


async def handle(store: list, text: str) -> int:
    await save_message(store, text)          # a coroutine does nothing until it is awaited
    return len(store)
