# Chapter 14 — Real-Time Features with Django Channels: extended material

The printed edition of *Building AI-Powered Apps* keeps each chapter short. This file holds the longer material that was moved here so that nothing is lost: the full hands-on lab, troubleshooting tables, checklists, further exercises, and sections that were condensed for print.


---

# Sections condensed for print


## The Streaming Engine › asyncio essentials for this chapter

| **Concept** | **What it means** |
|---|---|
| `async def` / `await` | An async function can pause at `await` while something slow happens; other tasks run meanwhile |
| **Task** (`asyncio.create_task`) | Starts a coroutine running in the background and returns a handle; our generation runs as a task so the connection can keep receiving messages (such as Stop) |
| **Cancellation** (`task.cancel()`) | Raises `CancelledError` inside the task at its next `await`. A task should clean up and finish; we use it for the Stop button and for disconnects |
| **Timeout** (`asyncio.timeout(seconds)`) | Cancels the block and raises `TimeoutError` if it takes too long |
| **Async generator** (`async for`, `yield`) | Produces values over time. AI streaming APIs are exactly this: each token chunk arrives later |
| `contextlib.aclosing` | Guarantees an async generator is closed (and its network connection released) even if we stop early |
| `asyncio.gather` | Wait for several awaitables |

One important rule: **swallowing** `CancelledError` **has consequences.** Normally you re-raise it. Our top-level generation task is the end of the line, so it catches cancellation on purpose to run its cleanup (save the partial answer, tell the client) and then finishes normally.


## The Streaming Engine › The tests

**chat/test_streaming.py**

```
import asyncio
import unittest

from .ai_fake import FakeProvider
from .streaming import Delta, GenerationBusy, GenerationManager, ProviderError, Usage

HISTORY = [{"role": "user", "content": "Explain Celery in one sentence"}]

class Harness:
    """Collects what the manager sends and saves, standing in for a WebSocket and the database."""

    def __init__(self, provider, **kwargs):
        self.sent: list[dict] = []
        self.saved: list[tuple] = []
        self.fail_sends = False
        self.manager = GenerationManager(provider, self.send, self.save_reply, **kwargs)

    async def send(self, message):
        if self.fail_sends:
            raise ConnectionError("client went away")
        self.sent.append(message)

    async def save_reply(self, conversation, text, usage, status):
        self.saved.append((conversation, text, usage, status))
        return f"msg_{len(self.saved)}"

    def types(self):
        return [m["type"] for m in self.sent]

    async def wait_idle(self):
        while self.manager.active:
            await asyncio.sleep(0.005)

    def start(self):
        gid = self.manager.reserve()
        self.manager.run(gid, conversation="conv-1", messages=HISTORY)
        return gid

class FlakyProvider:
    name = "flaky"

    async def stream(self, messages):
        yield Delta("Hello ")
        raise ProviderError("503 overloaded")

class SlowProvider:
    name = "slow"

    async def stream(self, messages):
        yield Delta("start ")
        await asyncio.sleep(10)
        yield Delta("never")

class BrokenProvider:
    name = "broken"

    async def stream(self, messages):
        raise RuntimeError("bug")
        yield Delta("unreachable")

class NoUsageProvider:
    name = "nousage"

    async def stream(self, messages):
        yield Delta("x" * 40)

class GenerationManagerTests(unittest.IsolatedAsyncioTestCase):
    async def test_streams_deltas_then_ends_and_saves_once(self):
        h = Harness(FakeProvider(delay=0, reply="one two three"))
        gid = h.start()
        await h.wait_idle()
        self.assertEqual(h.types(), ["assistant.delta"] * 3 + ["assistant.end"])
        end = h.sent[-1]["data"]
        self.assertEqual((end["generation_id"], end["status"], end["message_id"]), (gid, "completed", "msg_1"))
        self.assertEqual(len(h.saved), 1)
        self.assertEqual(h.saved[0][1], "one two three ")
        self.assertGreater(end["usage"]["output_tokens"], 0)

    async def test_cancel_keeps_the_partial_answer(self):
        h = Harness(FakeProvider(delay=0.02, reply="a b c d e f g h i j"))
        gid = h.start()
        await asyncio.sleep(0.07)
        self.assertTrue(await h.manager.cancel(gid))
        await h.wait_idle()
        self.assertEqual(h.sent[-1]["type"], "assistant.end")
        self.assertEqual(h.sent[-1]["data"]["status"], "canceled")
        self.assertEqual(len(h.saved), 1)
        self.assertEqual(h.saved[0][3], "canceled")
        self.assertLess(len(h.saved[0][1].split()), 10)           # not the full answer

    async def test_cancel_unknown_generation_returns_false(self):
        h = Harness(FakeProvider(delay=0))
        self.assertFalse(await h.manager.cancel("gen_nope"))

    async def test_provider_failure_sends_error_and_keeps_partial_text(self):
        h = Harness(FlakyProvider())
        h.start()
        await h.wait_idle()
        self.assertEqual(h.types(), ["assistant.delta", "assistant.error"])
        self.assertEqual(h.sent[-1]["data"]["code"], "upstream_unavailable")
        self.assertEqual(h.saved[0][3], "failed")

    async def test_timeout_is_reported(self):
        h = Harness(SlowProvider(), timeout=0.05)
        h.start()
        await h.wait_idle()
        self.assertEqual(h.sent[-1]["type"], "assistant.error")
        self.assertEqual(h.sent[-1]["data"]["code"], "generation_timeout")

    async def test_unexpected_exception_becomes_generic_error(self):
        h = Harness(BrokenProvider())
        h.start()
        await h.wait_idle()
        self.assertEqual(h.sent[-1]["data"]["code"], "generation_failed")
        self.assertEqual(h.saved, [])                                # nothing to store

    async def test_only_one_generation_at_a_time(self):
        h = Harness(FakeProvider(delay=0.01, reply="a b c"))
        first = h.start()
        with self.assertRaises(GenerationBusy):
            h.manager.reserve()
        await h.wait_idle()
        self.assertTrue(h.manager.reserve().startswith("gen_"))      # free again after the first finished
        self.assertTrue(first.startswith("gen_"))

    async def test_release_frees_an_unused_reservation(self):
        h = Harness(FakeProvider(delay=0))
        gid = h.manager.reserve()
        h.manager.release(gid)
        self.assertEqual(h.manager.active, 0)

    async def test_usage_is_estimated_when_provider_reports_none(self):
        h = Harness(NoUsageProvider())
        h.start()
        await h.wait_idle()
        usage = h.saved[0][2]
        self.assertEqual(usage.output_tokens, 10)                    # 40 characters / 4
        self.assertGreater(usage.input_tokens, 0)

    async def test_client_disconnect_stops_generation_and_saves_partial(self):
        h = Harness(FakeProvider(delay=0.01, reply="a b c d e f g h"))
        h.start()
        await asyncio.sleep(0.035)
        h.fail_sends = True                                          # the socket just died
        await h.wait_idle()
        self.assertEqual(h.saved[0][3], "canceled")
        self.assertLess(len(h.saved[0][1].split()), 8)

    async def test_cancel_all_on_disconnect(self):
        h = Harness(FakeProvider(delay=0.05, reply="a b c d e f g h"))
        h.start()
        await asyncio.sleep(0.06)
        await h.manager.cancel_all()
        self.assertEqual(h.manager.active, 0)
        self.assertEqual(len(h.saved), 1)

if __name__ == "__main__":
    unittest.main()
```

Run both test files. They need **no Django, no Channels and no network**; from the `backend/` folder:

**terminal**

```bash
python -m unittest chat.test_protocol chat.test_streaming -v
```

**output (abridged; verified)**

```text
test_cancel_all_on_disconnect ... ok
test_cancel_keeps_the_partial_answer ... ok
test_cancel_unknown_generation_returns_false ... ok
test_client_disconnect_stops_generation_and_saves_partial ... ok
test_only_one_generation_at_a_time ... ok
test_provider_failure_sends_error_and_keeps_partial_text ... ok
test_streams_deltas_then_ends_and_saves_once ... ok
test_timeout_is_reported ... ok
test_unexpected_exception_becomes_generic_error ... ok     (a logged traceback appears: that is expected)
test_usage_is_estimated_when_provider_reports_none ... ok
... (13 protocol tests) ...

Ran 24 tests in 0.3s
OK
```

The traceback printed during `test_unexpected_exception_becomes_generic_error` is the engine **logging the deliberate bug** the test injects. It is how you would see a real failure in production logs.


## A Client That Survives Bad Networks › Testing the client with a fake clock

Reconnection logic is notoriously hard to test with real timers. The test file replaces both the **clock** and the **socket** with fakes, so nine behaviors run in milliseconds, deterministically:

**reconnecting-socket.test.mjs**

```
import assert from "node:assert/strict";
import { test } from "node:test";
import { ReconnectingSocket } from "./reconnecting-socket.js";

// ---- test doubles: a fake clock and a fake socket -------------------------------------------
function makeClock() {
  let now = 0, nextId = 1;
  const tasks = new Map();
  return {
    timers: {
      setTimeout: (fn, ms) => { const id = nextId++; tasks.set(id, { at: now + ms, fn }); return id; },
      clearTimeout: (id) => tasks.delete(id),
      setInterval: (fn, ms) => { const id = nextId++; tasks.set(id, { at: now + ms, fn, every: ms }); return id; },
      clearInterval: (id) => tasks.delete(id),
    },
    async advance(ms) {
      const end = now + ms;
      for (;;) {
        const due = [...tasks.entries()].filter(([, t]) => t.at <= end).sort((a, b) => a[1].at - b[1].at)[0];
        if (!due) break;
        const [id, task] = due;
        now = task.at;
        if (task.every) task.at += task.every; else tasks.delete(id);
        task.fn();
        await Promise.resolve();
      }
      now = end;
    },
  };
}

function makeFactory() {
  const sockets = [];
  const createSocket = (url) => {
    const s = { url, readyState: 0, sent: [],
      send(data) { this.sent.push(JSON.parse(data)); },
      close(code) { this.readyState = 3; this.onclose && this.onclose({ code }); },
      open() { this.readyState = 1; this.onopen(); },
      drop(code = 1006) { this.readyState = 3; this.onclose({ code }); },
      receive(obj) { this.onmessage({ data: JSON.stringify(obj) }); } };
    sockets.push(s);
    return s;
  };
  return { sockets, createSocket };
}

const setup = (extra = {}) => {
  const clock = makeClock();
  const { sockets, createSocket } = makeFactory();
  const statuses = [], messages = [];
  const client = new ReconnectingSocket({
    url: "ws://test/ws/chat/", createSocket, timers: clock.timers, random: () => 1, // 1 = longest delay, predictable
    onStatus: (s) => statuses.push(s), onMessage: (m) => messages.push(m), ...extra });
  return { clock, sockets, statuses, messages, client };
};

test("connects, reports status and delivers messages", async () => {
  const { sockets, statuses, messages, client } = setup();
  client.connect();
  await Promise.resolve();
  sockets[0].open();
  sockets[0].receive({ type: "notification", data: { title: "Hi" } });
  assert.deepEqual(statuses, ["connecting", "open"]);
  assert.equal(messages[0].type, "notification");
});

test("messages sent while offline are queued and flushed on open", async () => {
  const { sockets, client } = setup();
  client.connect();
  await Promise.resolve();
  assert.equal(client.send({ type: "message.send", id: "c-1" }), true);   // still connecting
  sockets[0].open();
  assert.deepEqual(sockets[0].sent, [{ type: "message.send", id: "c-1" }]);
});

test("the queue has a limit", async () => {
  const { client } = setup({ maxQueue: 2 });
  client.connect();
  await Promise.resolve();
  assert.deepEqual([1, 2, 3].map((n) => client.send({ n })), [true, true, false]);
});

test("reconnects with exponential backoff and resets after success", async () => {
  const { clock, sockets, statuses, client } = setup();
  client.connect();
  await Promise.resolve();
  sockets[0].drop();                       // attempt 0 -> waits up to 500 ms
  await clock.advance(499); await Promise.resolve();
  assert.equal(sockets.length, 1);
  await clock.advance(1); await Promise.resolve();
  assert.equal(sockets.length, 2);
  sockets[1].drop();                       // attempt 1 -> waits up to 1000 ms
  await clock.advance(1000); await Promise.resolve();
  assert.equal(sockets.length, 3);
  sockets[2].open();                       // success resets the counter
  sockets[2].drop();
  await clock.advance(500); await Promise.resolve();
  assert.equal(sockets.length, 4);
  assert.ok(statuses.includes("reconnecting"));
});

test("backoff never exceeds the maximum", async () => {
  const { clock, sockets, client } = setup({ maxDelayMs: 2000 });
  client.connect();
  await Promise.resolve();
  for (let i = 0; i < 8; i++) {
    sockets[sockets.length - 1].drop();
    await clock.advance(2000); await Promise.resolve();
  }
  assert.equal(sockets.length, 9);         // every retry happened within 2000 ms
});

test("an unauthorized close (4401) stops retrying", async () => {
  const { clock, sockets, statuses, client } = setup();
  client.connect();
  await Promise.resolve();
  sockets[0].open();
  sockets[0].drop(4401);
  await clock.advance(60000); await Promise.resolve();
  assert.equal(sockets.length, 1);
  assert.equal(statuses.at(-1), "unauthorized");
});

test("heartbeat sends ping, and a missing pong forces a reconnect", async () => {
  const { clock, sockets, client } = setup({ heartbeatMs: 1000, pongTimeoutMs: 300 });
  client.connect();
  await Promise.resolve();
  sockets[0].open();
  await clock.advance(1000);
  assert.deepEqual(sockets[0].sent.at(-1), { type: "ping" });
  sockets[0].receive({ type: "pong", data: {} });          // healthy: no reconnect
  await clock.advance(400); await Promise.resolve();
  assert.equal(sockets.length, 1);
  await clock.advance(700);                                // next ping goes out...
  await clock.advance(300); await Promise.resolve();       // ...and no pong arrives
  await clock.advance(500); await Promise.resolve();
  assert.equal(sockets.length, 2);
});

test("url can be a function that returns a fresh ticket each time", async () => {
  let n = 0;
  const { clock, sockets, client } = setup({ url: async () => `ws://test/ws/chat/?ticket=t${++n}` });
  client.connect();
  await Promise.resolve(); await Promise.resolve();
  sockets[0].drop();
  await clock.advance(500); await Promise.resolve(); await Promise.resolve();
  assert.deepEqual(sockets.map((s) => s.url), ["ws://test/ws/chat/?ticket=t1", "ws://test/ws/chat/?ticket=t2"]);
});

test("close() stops everything and does not reconnect", async () => {
  const { clock, sockets, client } = setup();
  client.connect();
  await Promise.resolve();
  sockets[0].open();
  client.close();
  await clock.advance(60000); await Promise.resolve();
  assert.equal(sockets.length, 1);
  assert.equal(client.status, "closed");
});
```

**terminal (verified)**

```bash
node --test reconnecting-socket.test.mjs

ok 1 - connects, reports status and delivers messages
ok 2 - messages sent while offline are queued and flushed on open
ok 3 - the queue has a limit
ok 4 - reconnects with exponential backoff and resets after success
ok 5 - backoff never exceeds the maximum
ok 6 - an unauthorized close (4401) stops retrying
ok 7 - heartbeat sends ping, and a missing pong forces a reconnect
ok 8 - url can be a function that returns a fresh ticket each time
ok 9 - close() stops everything and does not reconnect
# tests 9   # pass 9   # fail 0
```


## Testing Channels Code

You now have three levels of tests, from fastest to slowest:

| **Level** | **What** | **Speed / needs** |
|---|---|---|
| **Pure unit tests** | Protocol and streaming engine (24 tests), client (9 tests) | Milliseconds; nothing installed |
| **Service tests** (Chapter 11) | Ownership, billing consistency, usage | Needs the database |
| **Consumer integration tests** | A real consumer through `WebsocketCommunicator`: auth, ping, validation, a full streamed exchange, ownership, quota, notifications | Needs Django, Channels, database |

**chat/test_consumers.py**

```
"""Integration tests for the WebSocket consumer (needs Django and Channels installed)."""
from unittest import mock

from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import TransactionTestCase, override_settings

from . import services
from .ai_fake import FakeProvider
from .consumers import ChatConsumer
from .models import Message, UsageRecord

User = get_user_model()
IN_MEMORY_LAYER = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}

async def receive_until(communicator, wanted_type, limit=20):
    """Collect JSON messages until one with the wanted type arrives."""
    received = []
    for _ in range(limit):
        message = await communicator.receive_json_from(timeout=3)
        received.append(message)
        if message["type"] == wanted_type:
            return received
    raise AssertionError(f"never received {wanted_type}; got {[m['type'] for m in received]}")

@override_settings(CHANNEL_LAYERS=IN_MEMORY_LAYER, AI_PROVIDER="fake")
class ChatConsumerTests(TransactionTestCase):
    """TransactionTestCase, because the consumer talks to the database from other threads."""

    async def connect_as(self, user):
        communicator = WebsocketCommunicator(ChatConsumer.as_asgi(), "/ws/chat/")
        communicator.scope["user"] = user                # normally set by the authentication middleware
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        return communicator

    async def make_user_and_conversation(self, email="ada@example.com"):
        user = await database_sync_to_async(User.objects.create_user)(email=email, password="a-long-test-password")
        conversation = await database_sync_to_async(services.create_conversation)(user=user, title="T")
        return user, conversation

    async def test_anonymous_users_are_closed_with_4401(self):
        communicator = await self.connect_as(AnonymousUser())
        output = await communicator.receive_output(timeout=3)
        self.assertEqual((output["type"], output["code"]), ("websocket.close", 4401))

    async def test_ping_gets_pong(self):
        user, _ = await self.make_user_and_conversation()
        communicator = await self.connect_as(user)
        await communicator.send_json_to({"type": "ping", "id": "p-1"})
        self.assertEqual(await communicator.receive_json_from(timeout=3), {"type": "pong", "data": {}, "ref": "p-1"})
        await communicator.disconnect()

    async def test_invalid_json_returns_an_error_message(self):
        user, _ = await self.make_user_and_conversation()
        communicator = await self.connect_as(user)
        await communicator.send_to(text_data="{broken")
        reply = await communicator.receive_json_from(timeout=3)
        self.assertEqual((reply["type"], reply["data"]["code"]), ("error", "invalid_json"))
        await communicator.disconnect()

    async def test_message_streams_and_is_saved_and_billed(self):
        user, conversation = await self.make_user_and_conversation()
        with mock.patch("chat.consumers.get_provider", return_value=FakeProvider(delay=0, reply="hello big world")):
            communicator = await self.connect_as(user)
            await communicator.send_json_to({"type": "message.send", "id": "c-1", "data": {
                "conversation_id": str(conversation.public_id), "content": "Hi there"}})
            received = await receive_until(communicator, "assistant.end")
            await communicator.disconnect()

        types = [m["type"] for m in received]
        self.assertEqual(types[0], "message.accepted")
        self.assertEqual(received[0]["ref"], "c-1")
        self.assertEqual(types.count("assistant.delta"), 3)
        self.assertEqual(received[-1]["data"]["status"], "completed")
        self.assertEqual(await database_sync_to_async(Message.objects.count)(), 2)          # user + assistant
        self.assertEqual(await database_sync_to_async(UsageRecord.objects.filter(user=user).count)(), 1)

    async def test_other_users_conversation_is_not_found(self):
        _, conversation = await self.make_user_and_conversation("ada@example.com")
        intruder, _ = await self.make_user_and_conversation("bo@example.com")
        communicator = await self.connect_as(intruder)
        await communicator.send_json_to({"type": "message.send", "data": {
            "conversation_id": str(conversation.public_id), "content": "let me in"}})
        reply = await communicator.receive_json_from(timeout=3)
        self.assertEqual((reply["type"], reply["data"]["code"]), ("error", "not_found"))
        await communicator.disconnect()

    @override_settings(FREE_MONTHLY_TOKEN_LIMIT=10)
    async def test_quota_exceeded(self):
        user, conversation = await self.make_user_and_conversation()
        await database_sync_to_async(UsageRecord.objects.create)(user=user, input_tokens=20, output_tokens=0)
        communicator = await self.connect_as(user)
        await communicator.send_json_to({"type": "message.send", "data": {
            "conversation_id": str(conversation.public_id), "content": "hello"}})
        reply = await communicator.receive_json_from(timeout=3)
        self.assertEqual(reply["data"]["code"], "quota_exceeded")
        await communicator.disconnect()

    async def test_notifications_reach_the_users_group(self):
        from channels.layers import get_channel_layer
        user, _ = await self.make_user_and_conversation()
        communicator = await self.connect_as(user)
        await get_channel_layer().group_send(
            f"user_{user.pk}", {"type": "notify", "data": {"kind": "payment", "title": "Payment received", "body": ""}})
        reply = await communicator.receive_json_from(timeout=3)
        self.assertEqual((reply["type"], reply["data"]["title"]), ("notification", "Payment received"))
        await communicator.disconnect()
```


### Points to notice

- `WebsocketCommunicator` drives a consumer without a network. We assign `scope["user"]` ourselves, standing in for the authentication middleware.
- `TransactionTestCase` **instead of** `TestCase`**.** The consumer touches the database from other threads (through `database_sync_to_async`), which cannot see the uncommitted data of a wrapped `TestCase` transaction.
- `override_settings(CHANNEL_LAYERS=...)` gives the tests an in-memory layer, so no Redis is needed.
- `mock.patch("chat.consumers.get_provider", ...)` swaps in a deterministic fake with zero delay, so the stream is fast and predictable.
- `receive_until` reads messages until the expected type arrives, with a timeout so a failing test fails fast instead of hanging.
**terminal**

```bash
python manage.py test chat                # everything in chat: services, protocol, streaming, consumers
python manage.py test chat.test_consumers
```


## Running Channels in Production › Pitfalls in async code

| **Pitfall** | **Fix** |
|---|---|
| A blocking call (`requests.get`, `time.sleep`, big CPU loop) inside an `async def` | Use async libraries (`httpx`, the provider’s async client), `asyncio.sleep`, or `sync_to_async`/`database_sync_to_async` for blocking code |
| Database access in async code without wrapping | `SynchronousOnlyOperation` error: wrap with `database_sync_to_async` |
| Forgetting `await` (a coroutine that never runs) | Python warns "coroutine ... was never awaited"; treat the warning as a bug |
| Unbounded memory per connection | Keep per-connection state small; cap history length, queue sizes and message sizes |
| Leaked tasks after disconnect | Cancel in `disconnect` (we do); never start fire-and-forget tasks without tracking them |
| Stale database connections | `database_sync_to_async` closes old connections; do not hold ORM objects across long waits |
