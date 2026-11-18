import { CLOSE_AUTH_FAILED, SocketManager, SocketOptions, WebSocketLike } from "../src/socket";
import { flushPromises } from "./helpers";

class FakeSocket implements WebSocketLike {
  readyState = 0;
  sent: any[] = [];
  closedWith?: [number | undefined, string | undefined];
  onopen: WebSocketLike["onopen"] = null;
  onmessage: WebSocketLike["onmessage"] = null;
  onclose: WebSocketLike["onclose"] = null;
  onerror: WebSocketLike["onerror"] = null;
  constructor(readonly url: string) {}
  send(data: string) { this.sent.push(JSON.parse(data)); }
  close(code?: number, reason?: string) { this.closedWith = [code, reason]; }
  // helpers the tests use to play the server
  open() { this.readyState = 1; this.onopen?.({}); }
  say(message: unknown) { this.onmessage?.({ data: typeof message === "string" ? message : JSON.stringify(message) }); }
  drop(code = 1006) { this.onclose?.({ code }); }
}

class Clock {
  now = 0;
  private tasks: Array<{ at: number; fn: () => void; cancelled: boolean }> = [];
  schedule = (fn: () => void, ms: number) => {
    const task = { at: this.now + ms, fn, cancelled: false };
    this.tasks.push(task);
    return () => { task.cancelled = true; };
  };
  advance(ms: number) {
    const end = this.now + ms;
    for (;;) {
      const due = this.tasks.filter((t) => !t.cancelled && t.at <= end).sort((a, b) => a.at - b.at)[0];
      if (!due) break;
      this.tasks = this.tasks.filter((t) => t !== due);
      this.now = due.at;
      due.fn();
    }
    this.now = end;
  }
  get pendingTasks() { return this.tasks.filter((t) => !t.cancelled).length; }
}

function setup(extra: Partial<SocketOptions> = {}, token: string | null = "tok-123") {
  const clock = new Clock();
  const sockets: FakeSocket[] = [];
  const manager = new SocketManager({
    url: "wss://api.example.com/ws/chat/",
    getToken: async () => token,
    createSocket: (url) => { const s = new FakeSocket(url); sockets.push(s); return s; },
    schedule: clock.schedule, now: () => clock.now, random: () => 0.5,
    heartbeatMs: 25_000, pongTimeoutMs: 10_000, authTimeoutMs: 10_000, baseDelayMs: 1000, maxDelayMs: 30_000, stableAfterMs: 10_000,
    ...extra,
  });
  const states: string[] = [];
  manager.onState((s) => states.push(s));
  const messages: unknown[] = [];
  manager.onMessage((m) => messages.push(m));
  const authFailed = jest.fn();
  manager.onAuthFailed(authFailed);
  /** Connect and complete the handshake. */
  const connectFully = async () => {
    manager.connect();
    const s = sockets[sockets.length - 1]!;
    s.open();
    await flushPromises();
    s.say({ type: "auth_ok" });
    return s;
  };
  return { manager, sockets, clock, states, messages, authFailed, connectFully };
}

test("the token is sent as the first message, never in the address", async () => {
  const { manager, sockets } = setup();
  manager.connect();
  sockets[0]!.open();
  await flushPromises();
  expect(sockets[0]!.url).toBe("wss://api.example.com/ws/chat/");
  expect(sockets[0]!.url).not.toContain("tok-123");
  expect(sockets[0]!.sent).toEqual([{ type: "auth", token: "tok-123" }]);
  expect(manager.getState()).toBe("authenticating");
});

test("the socket is open only after the server accepts the token", async () => {
  const { manager, connectFully, states } = setup();
  await connectFully();
  expect(manager.getState()).toBe("open");
  expect(states).toEqual(["connecting", "authenticating", "open"]);
});

test("messages before authentication are not passed on", async () => {
  const { manager, sockets, messages } = setup();
  manager.connect();
  sockets[0]!.open();
  await flushPromises();
  sockets[0]!.say({ type: "chat.message", text: "sneaky" });
  expect(messages).toEqual([]);
  sockets[0]!.say({ type: "auth_ok" });
  sockets[0]!.say({ type: "chat.message", text: "real" });
  expect(messages).toEqual([{ type: "chat.message", text: "real" }]);
});

test("garbage is ignored and does not crash the listener", async () => {
  const { sockets, messages, connectFully } = setup();
  const s = await connectFully();
  s.say("not json {");
  s.say(JSON.stringify(42));
  s.say({ type: "chat.message", n: 1 });
  expect(messages).toEqual([{ type: "chat.message", n: 1 }]);
  expect(sockets).toHaveLength(1);
});

test("messages sent while disconnected are delivered after sign-in completes", async () => {
  const { manager, sockets } = setup();
  expect(manager.send({ type: "chat.send", text: "queued" })).toBe(true);
  manager.connect();
  sockets[0]!.open();
  await flushPromises();
  expect(sockets[0]!.sent).toHaveLength(1); // only the auth message so far
  sockets[0]!.say({ type: "auth_ok" });
  expect(sockets[0]!.sent[1]).toEqual({ type: "chat.send", text: "queued" });
  manager.send({ type: "chat.send", text: "live" });
  expect(sockets[0]!.sent[2]).toEqual({ type: "chat.send", text: "live" });
});

test("the waiting queue is bounded", () => {
  const { manager } = setup({ maxQueued: 2 });
  expect([1, 2, 3].map((n) => manager.send({ n }))).toEqual([true, true, false]);
});

test("a dropped connection is retried with growing delays", async () => {
  const { manager, sockets, clock, connectFully } = setup();
  const first = await connectFully();
  first.drop(1006);
  expect(manager.getState()).toBe("waiting");
  clock.advance(749); expect(sockets).toHaveLength(1);   // attempt 0: 1000 ms ceiling, random 0.5 = 750 ms
  clock.advance(1);   expect(sockets).toHaveLength(2);
  sockets[1]!.drop(1006);                                 // never opened: the next wait doubles
  clock.advance(1499); expect(sockets).toHaveLength(2);
  clock.advance(1);   expect(sockets).toHaveLength(3);
  sockets[2]!.drop(1006);
  clock.advance(2999); expect(sockets).toHaveLength(3);
  clock.advance(1);   expect(sockets).toHaveLength(4);
});

test("the delay stops growing at the maximum", async () => {
  const { sockets, clock, connectFully } = setup({ maxDelayMs: 4000 });
  let s = await connectFully();
  for (let i = 0; i < 8; i++) { s.drop(1006); clock.advance(10_000); s = sockets[sockets.length - 1]!; }
  s.drop(1006);
  clock.advance(2999); const before = sockets.length;
  clock.advance(1);
  expect(sockets.length).toBe(before + 1); // 4000 ms ceiling, random 0.5 = 3000 ms, no more
});

test("a connection that stayed up for a while resets the delay", async () => {
  const { sockets, clock, connectFully } = setup();
  let s = await connectFully();
  for (let i = 0; i < 3; i++) { s.drop(1006); clock.advance(10_000); s = sockets[sockets.length - 1]!; }
  s.open(); await flushPromises(); s.say({ type: "auth_ok" });
  clock.advance(12_000);                 // stable for longer than stableAfterMs
  s.drop(1006);
  clock.advance(749); const n = sockets.length;
  clock.advance(1);
  expect(sockets.length).toBe(n + 1);    // back to the first, short delay
});

test("a refused token is reported, and the socket does NOT keep retrying", async () => {
  const { manager, sockets, clock, authFailed, connectFully } = setup();
  const s = await connectFully();
  s.drop(CLOSE_AUTH_FAILED);
  expect(authFailed).toHaveBeenCalledTimes(1);
  expect(manager.getState()).toBe("closed");
  clock.advance(120_000);
  expect(sockets).toHaveLength(1);
  manager.connect(); // after the app has refreshed the token
  expect(sockets).toHaveLength(2);
});

test("having no token at all is an authentication failure", async () => {
  const { manager, sockets, authFailed } = setup({}, null);
  manager.connect();
  sockets[0]!.open();
  await flushPromises();
  expect(authFailed).toHaveBeenCalledTimes(1);
  expect(manager.getState()).toBe("closed");
});

test("a server that never answers the token is given up on and retried", async () => {
  const { manager, sockets, clock } = setup();
  manager.connect();
  sockets[0]!.open();
  await flushPromises();
  clock.advance(10_000);
  expect(manager.getState()).toBe("waiting");
  clock.advance(1000);
  expect(sockets).toHaveLength(2);
});

test("it pings on a schedule, and keeps going while pongs come back", async () => {
  const { sockets, clock, connectFully } = setup();
  const s = await connectFully();
  clock.advance(24_999); expect(s.sent.filter((m) => m.type === "ping")).toHaveLength(0);
  clock.advance(1);      expect(s.sent.filter((m) => m.type === "ping")).toHaveLength(1);
  s.say({ type: "pong" });
  clock.advance(25_000); expect(s.sent.filter((m) => m.type === "ping")).toHaveLength(2);
  expect(sockets).toHaveLength(1);
});

test("a connection that stops answering pings is replaced", async () => {
  const { manager, sockets, clock, connectFully } = setup();
  const s = await connectFully();
  clock.advance(25_000);                 // ping sent, no pong
  clock.advance(10_000);                 // pong timeout
  expect(manager.getState()).toBe("waiting");
  expect(s.closedWith).toBeDefined();
  clock.advance(1000);
  expect(sockets).toHaveLength(2);
});

test("going to the background pauses, and coming back reconnects", async () => {
  const { manager, sockets, clock, connectFully } = setup();
  const s = await connectFully();
  manager.pause();
  expect(manager.getState()).toBe("paused");
  expect(s.closedWith).toBeDefined();
  clock.advance(60_000);
  expect(sockets).toHaveLength(1);
  manager.resume();
  expect(sockets).toHaveLength(2);
});

test("while offline it waits instead of trying, and reconnects when the network returns", async () => {
  const { manager, sockets, clock, connectFully } = setup();
  const s = await connectFully();
  manager.setOnline(false);
  s.drop(1006);
  clock.advance(60_000);
  expect(sockets).toHaveLength(1);       // no attempts while offline
  manager.setOnline(true);
  expect(sockets).toHaveLength(2);       // straight away, no need to wait out the timer
});

test("close() stops everything for good", async () => {
  const { manager, sockets, clock, connectFully } = setup();
  const s = await connectFully();
  manager.close();
  s.drop(1006);
  clock.advance(120_000);
  expect(sockets).toHaveLength(1);
  expect(manager.getState()).toBe("closed");
  expect(clock.pendingTasks).toBe(0);
});

test("events from an old socket cannot disturb the new one", async () => {
  const { manager, sockets, clock, messages, connectFully } = setup();
  const old = await connectFully();
  old.drop(1006);
  clock.advance(1000);
  const fresh = sockets[1]!;
  fresh.open(); await flushPromises(); fresh.say({ type: "auth_ok" });
  old.say({ type: "chat.message", text: "ghost" });  // a late message from the dead connection
  old.drop(1006);                                    // and a late close event
  expect(messages).toEqual([]);
  expect(manager.getState()).toBe("open");
  expect(sockets).toHaveLength(2);
});

test("a token lookup that finishes after the socket was closed sends nothing", async () => {
  let release!: (token: string) => void;
  const slowToken = new Promise<string>((resolve) => (release = resolve));
  const { manager, sockets } = setup({ getToken: () => slowToken });
  manager.connect();
  sockets[0]!.open();                    // the handshake starts and waits for the token
  manager.close();                       // the user leaves before the token is ready
  release("tok-late");
  await flushPromises();
  expect(sockets[0]!.sent).toEqual([]);  // the late token is not sent down a dead socket
  expect(manager.getState()).toBe("closed");
});
