"""Run the streaming engine WITHOUT Django, Channels or an API key: a conversation in your terminal.

    python simulate_chat.py            # a full answer
    python simulate_chat.py 0.5        # the user presses Stop after 0.5 seconds
"""
import asyncio
import json
import sys

from chat.ai_fake import FakeProvider
from chat.protocol import parse_client_message, server_message
from chat.streaming import GenerationManager

async def main(cancel_after: float | None) -> None:
    async def send(message: dict) -> None:                 # stands in for websocket.send_json
        print("<-", json.dumps(message))

    async def save_reply(conversation, text, usage, status) -> str:     # stands in for the database
        print(f"   [saved as {status}: {text!r}, usage={usage}]")
        return "msg_2"

    manager = GenerationManager(FakeProvider(delay=0.08), send, save_reply)

    frame = json.dumps({"type": "message.send", "id": "c-1",
                        "data": {"conversation_id": "conv-1", "content": "Explain WebSockets"}})
    print("->", frame)
    envelope = parse_client_message(frame)                 # validation happens here

    generation_id = manager.reserve()
    await send(server_message("message.accepted", {"message_id": "msg_1", "generation_id": generation_id}, envelope.id))
    manager.run(generation_id, conversation="conv-1", messages=[{"role": "user", "content": envelope.data["content"]}])

    if cancel_after is not None:
        await asyncio.sleep(cancel_after)
        print("-> generation.cancel")
        await manager.cancel(generation_id)
    while manager.active:
        await asyncio.sleep(0.05)

if __name__ == "__main__":
    asyncio.run(main(float(sys.argv[1]) if len(sys.argv) > 1 else None))
