# Chapter 5 — How the Web Works: extended material

The printed edition of *Building AI-Powered Apps* keeps each chapter short. This file holds the longer material that was moved here so that nothing is lost: the full hands-on lab, troubleshooting tables, checklists, further exercises, and sections that were condensed for print.


---

# Sections condensed for print


## Real-Time Communication: WebSockets and Streaming › A tiny WebSocket example

A minimal Python echo server using the `websockets` library (install with `pip install websockets`):

**ws_server.py**

```
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
```

And the client, pasted into the browser console (F12) or used in any web page:

**browser JavaScript**

```
const socket = new WebSocket("ws://localhost:8765");

socket.onopen = () => socket.send("hello server");
socket.onmessage = (event) => console.log("received:", event.data);
socket.onclose = () => console.log("connection closed");
socket.onerror = (error) => console.log("error", error);
```

Notice the shape: **events** (open, message, close, error) instead of a single response. Real apps add authentication, reconnection logic and message formats on top, which is exactly what Chapters 14 and 21 teach.

> **Why AI answers feel instant**
>
> AI models generate text token by token. Instead of waiting for the full answer, the backend forwards each token as it arrives, over a WebSocket or SSE connection. The user starts reading after a fraction of a second, even if the whole answer takes ten seconds.


## Databases › Using PostgreSQL from Chapter 2

If your Docker services from Chapter 2 are running, open a PostgreSQL shell and run the schema above:

**terminal**

```bash
cd ~/projects/local-services
docker compose up -d
docker compose exec db psql -U app -d app_db
```

| **psql command** | **Meaning** |
|---|---|
| `\dt` | List tables |
| `\d users` | Describe a table (columns, indexes, keys) |
| `\l` | List databases |
| `\x` | Toggle expanded output for wide rows |
| `\q` | Quit |

In Part III, Django will create tables for you from Python classes (**models**) through **migrations**, so you will rarely write `CREATE TABLE` by hand. Understanding what it generates, however, is what lets you design good models and debug slow queries.


## Databases › Indexes and performance in one paragraph

An index speeds up reads on the indexed columns but slows down writes slightly and uses space. Index columns you filter or join on often (foreign keys, email, created_at for sorting). You can inspect how PostgreSQL runs a query with `EXPLAIN ANALYZE SELECT ...;`: if you see "Seq Scan" on a huge table for a query that should return a few rows, you probably need an index. We return to this in Chapter 7.
