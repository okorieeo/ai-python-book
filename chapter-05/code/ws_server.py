# ws_server.py
import asyncio
from websockets.asyncio.server import serve

async def echo(websocket):
    async for message in websocket:           # runs for each incoming message
        await websocket.send(f"echo: {message}")

async def main():
    async with serve(echo, "localhost", 8765):
        print("WebSocket server on ws://localhost:8765")
        await asyncio.Future()                # run forever

asyncio.run(main())
