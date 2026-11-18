import assert from "node:assert/strict";
import { test } from "node:test";

import { ChatClient, UnauthorizedError, type SocketLike } from "./chat-client";
import type { ServerFrame } from "./chat-protocol";
import { chatReducer, initialChatState, type ChatState } from "./chat-state";

const frame = (state: ChatState, f: ServerFrame) => chatReducer(state, { type: "frame", frame: f });
const PLAN = { code: "free", name: "Free", daily_message_limit: 3 };

function conversationAfterStart(): ChatState {
  let s = frame(initialChatState, { type: "ready", plan: PLAN, usage: { used: 0, limit: 3 } });
  s = chatReducer(s, { type: "local.send", clientId: "c1", content: "Hi" });
  return frame(s, { type: "chat.started", client_id: "c1", conversation_id: "conv-1", title: "Hi", user_message_id: 1, assistant_message_id: 2 });
}

test("a streamed answer is assembled from deltas and finishes with the remaining quota", () => {
  let s = conversationAfterStart();
  assert.equal(s.busy, true);
  assert.deepEqual(s.messages.map((m) => [m.role, m.status]), [["user", "complete"], ["assistant", "streaming"]]);
  s = frame(s, { type: "chat.delta", assistant_message_id: 2, text: "Hel" });
  s = frame(s, { type: "chat.delta", assistant_message_id: 2, text: "lo" });
  s = frame(s, { type: "chat.done", assistant_message_id: 2, status: "complete", usage: { input_tokens: 5, output_tokens: 2 }, remaining: 2 });
  assert.equal(s.messages[1].content, "Hello");
  assert.equal(s.messages[1].status, "complete");
  assert.equal(s.busy, false);
  assert.deepEqual(s.usage, { used: 1, limit: 3 });
  assert.equal(s.conversationId, "conv-1");
});

test("a refused message disappears so it can be resent, and the limit banner appears", () => {
  let s = frame(initialChatState, { type: "ready", plan: PLAN, usage: { used: 3, limit: 3 } });
  assert.equal(s.limitReached, true);
  s = chatReducer(s, { type: "local.send", clientId: "c9", content: "one more" });
  s = frame(s, { type: "chat.error", code: "limit_reached", message: "Used all 3", client_id: "c9" });
  assert.equal(s.messages.length, 0);
  assert.equal(s.busy, false);
  assert.equal(s.error?.code, "limit_reached");
});

test("a plan upgrade pushed by the server lifts the limit without a refresh", () => {
  let s = frame(initialChatState, { type: "ready", plan: PLAN, usage: { used: 3, limit: 3 } });
  s = frame(s, { type: "plan.updated", plan: { code: "pro", name: "Pro", daily_message_limit: 500 } });
  assert.equal(s.limitReached, false);
  assert.equal(s.usage?.limit, 500);
  assert.equal(s.plan?.name, "Pro");
});

test("a dropped connection turns a half-written answer into a stopped one instead of spinning forever", () => {
  let s = frame(conversationAfterStart(), { type: "chat.delta", assistant_message_id: 2, text: "Par" });
  s = chatReducer(s, { type: "connection", status: "closed" });
  assert.equal(s.busy, false);
  assert.equal(s.messages[1].status, "stopped");
  assert.equal(s.messages[1].content, "Par");
});

test("a provider error keeps the partial text and marks the answer as failed", () => {
  let s = frame(conversationAfterStart(), { type: "chat.delta", assistant_message_id: 2, text: "Par" });
  s = frame(s, { type: "chat.error", code: "provider_error", message: "Model unavailable", assistant_message_id: 2 });
  assert.equal(s.messages[1].status, "error");
  assert.equal(s.messages[1].content, "Par");
  assert.equal(s.busy, false);
});

// ---- the client ------------------------------------------------------------------------------------
class FakeSocket implements SocketLike {
  static all: FakeSocket[] = [];
  sent: string[] = [];
  closedWith: number | undefined;
  onopen: SocketLike["onopen"] = null;
  onmessage: SocketLike["onmessage"] = null;
  onclose: SocketLike["onclose"] = null;
  onerror: SocketLike["onerror"] = null;
  constructor(public url: string) { FakeSocket.all.push(this); }
  send(d: string) { this.sent.push(d); }
  close(code?: number) { this.closedWith = code; }
}

function harness(getTicket?: () => Promise<string>) {
  FakeSocket.all = [];
  const timers: { fn: () => void; ms: number }[] = [];
  const statuses: string[] = [];
  const frames: ServerFrame[] = [];
  let n = 0;
  let unauthorized = 0;
  const client = new ChatClient({
    wsUrl: "ws://test/ws/chat/", getTicket: getTicket ?? (async () => `ticket-${++n}`),
    onFrame: (f) => frames.push(f), onStatus: (s) => statuses.push(s), onUnauthorized: () => { unauthorized++; },
    createSocket: (url) => new FakeSocket(url), random: () => 1,
    setTimer: (fn, ms) => { const t = { fn, ms }; timers.push(t); return () => { timers.splice(timers.indexOf(t), 1); }; },
  });
  return { client, timers, statuses, frames, unauthorized: () => unauthorized };
}
const tick = () => new Promise((r) => setImmediate(r));

test("connect asks for a ticket and puts it in the URL, once even if called twice", async () => {
  const h = harness();
  h.client.connect(); h.client.connect();
  await tick();
  assert.equal(FakeSocket.all.length, 1);
  assert.equal(FakeSocket.all[0].url, "ws://test/ws/chat/?ticket=ticket-1");
});

test("after a drop it reconnects with a FRESH ticket and growing delays; a ready frame resets the backoff", async () => {
  const h = harness();
  h.client.connect(); await tick();
  FakeSocket.all[0].onclose?.({ code: 1006 });
  assert.equal(h.timers.length, 1);
  assert.equal(h.timers[0].ms, 500);
  h.timers.shift()!.fn(); await tick();
  FakeSocket.all[1].onclose?.({ code: 1006 });
  assert.equal(h.timers[0].ms, 1000);
  h.timers.shift()!.fn(); await tick();
  assert.equal(FakeSocket.all[2].url, "ws://test/ws/chat/?ticket=ticket-3");
  FakeSocket.all[2].onmessage?.({ data: JSON.stringify({ type: "ready", plan: PLAN, usage: { used: 0, limit: 3 } }) });
  FakeSocket.all[2].onclose?.({ code: 1006 });
  assert.equal(h.timers[0].ms, 500);
});

test("delays are capped", () => {
  const h = harness();
  assert.equal(h.client.delayFor(20), 15_000);
});

test("close code 4401 means the login expired: tell the app and do NOT reconnect", async () => {
  const h = harness();
  h.client.connect(); await tick();
  FakeSocket.all[0].onclose?.({ code: 4401 });
  assert.equal(h.unauthorized(), 1);
  assert.equal(h.timers.length, 0);
});

test("a ticket request that is refused reports unauthorized; other failures retry", async () => {
  const refused = harness(async () => { throw new UnauthorizedError(); });
  refused.client.connect(); await tick();
  assert.equal(refused.unauthorized(), 1);
  assert.equal(refused.timers.length, 0);

  const flaky = harness(async () => { throw new Error("network down"); });
  flaky.client.connect(); await tick();
  assert.equal(flaky.unauthorized(), 0);
  assert.equal(flaky.timers.length, 1);
});

test("close() stops reconnecting for good and send() reports whether the socket is available", async () => {
  const h = harness();
  assert.equal(h.client.send({ type: "ping" }), false);
  h.client.connect(); await tick();
  assert.equal(h.client.send({ type: "chat.stop" }), true);
  assert.deepEqual(FakeSocket.all[0].sent, ['{"type":"chat.stop"}']);
  h.client.close();
  assert.equal(FakeSocket.all[0].closedWith, 1000);
  FakeSocket.all[0].onclose?.({ code: 1000 });
  assert.equal(h.timers.length, 0);
  assert.equal(h.client.send({ type: "ping" }), false);
});

test("garbage frames are ignored and valid ones are delivered", async () => {
  const h = harness();
  h.client.connect(); await tick();
  FakeSocket.all[0].onmessage?.({ data: "not json" });
  FakeSocket.all[0].onmessage?.({ data: JSON.stringify({ type: "pong" }) });
  assert.deepEqual(h.frames, [{ type: "pong" }]);
});
