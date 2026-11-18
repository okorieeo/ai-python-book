import { beforeEach, describe, expect, it } from "vitest";
import {
  backoffDelay,
  FatalSocketError,
  ReconnectingSocket,
  type ConnectionStatus,
  type WebSocketLike,
} from "./socket";

class FakeSocket implements WebSocketLike {
  static all: FakeSocket[] = [];
  readyState = 0;
  sent: string[] = [];
  closedWith: number | undefined;
  onopen: ((e: unknown) => void) | null = null;
  onmessage: ((e: { data: unknown }) => void) | null = null;
  onclose: ((e: { code: number }) => void) | null = null;
  onerror: ((e: unknown) => void) | null = null;
  constructor(public url: string) {
    FakeSocket.all.push(this);
  }
  send(data: string) { this.sent.push(data); }
  close(code?: number) { this.closedWith = code; this.readyState = 3; }
  // helpers the tests use to play the server's part
  serverOpens() { this.readyState = 1; this.onopen?.({}); }
  serverSends(data: unknown) { this.onmessage?.({ data }); }
  serverErrors() { this.onerror?.({}); }
  serverCloses(code: number) { this.readyState = 3; this.onclose?.({ code }); }
}

class FakeClock {
  now = 0;
  private next = 1;
  private timers = new Map<number, { at: number; fn: () => void }>();
  setTimer = (fn: () => void, ms: number) => {
    const id = this.next++;
    this.timers.set(id, { at: this.now + ms, fn });
    return id;
  };
  clearTimer = (id: unknown) => { this.timers.delete(id as number); };
  get pending() { return this.timers.size; }
  async advance(ms: number) {
    const end = this.now + ms;
    for (;;) {
      const due = [...this.timers.entries()]
        .filter(([, t]) => t.at <= end)
        .sort((a, b) => a[1].at - b[1].at)[0];
      if (!due) break;
      this.timers.delete(due[0]);
      this.now = due[1].at;
      due[1].fn();
      await flush();
    }
    this.now = end;
  }
}
const flush = () => new Promise<void>((r) => setTimeout(r, 0));

function setup(overrides: Partial<ConstructorParameters<typeof ReconnectingSocket>[0]> = {}) {
  const clock = new FakeClock();
  const messages: unknown[] = [];
  const statuses: ConnectionStatus[] = [];
  let tickets = 0;
  const socket = new ReconnectingSocket({
    url: "wss://api.test/ws/chat/",
    getTicket: async () => `ticket-${++tickets}`,
    onMessage: (d) => messages.push(d),
    onStatus: (s) => statuses.push(s),
    createSocket: (url) => new FakeSocket(url),
    setTimer: clock.setTimer,
    clearTimer: clock.clearTimer,
    random: () => 1, // always the maximum delay, so the numbers are predictable
    baseDelayMs: 500,
    maxDelayMs: 4_000,
    heartbeatMs: 25_000,
    pongTimeoutMs: 10_000,
    stableMs: 10_000,
    ...overrides,
  });
  return { socket, clock, messages, statuses, ticketsIssued: () => tickets };
}
const last = () => FakeSocket.all[FakeSocket.all.length - 1]!;

beforeEach(() => { FakeSocket.all = []; });

describe("backoffDelay", () => {
  it("doubles each attempt and stops at the cap", () => {
    const delays = [0, 1, 2, 3, 4, 5].map((n) => backoffDelay(n, 500, 4_000, () => 1));
    expect(delays).toEqual([500, 1000, 2000, 4000, 4000, 4000]);
  });
  it("uses a random fraction of the ceiling (full jitter)", () => {
    expect(backoffDelay(2, 500, 30_000, () => 0.5)).toBe(1000);
    expect(backoffDelay(2, 500, 30_000, () => 0)).toBe(0);
  });
});

describe("ReconnectingSocket: connecting", () => {
  it("fetches a ticket, puts it in the URL, and reports open", async () => {
    const { socket, statuses } = setup();
    socket.connect();
    await flush();
    expect(last().url).toBe("wss://api.test/ws/chat/?ticket=ticket-1");
    last().serverOpens();
    expect(socket.currentStatus).toBe("open");
    expect(statuses).toEqual(["connecting", "open"]);
  });

  it("encodes the ticket and respects an existing query string", async () => {
    const { socket } = setup({ url: "wss://api.test/ws/?v=1", getTicket: async () => "a b&c" });
    socket.connect();
    await flush();
    expect(last().url).toBe("wss://api.test/ws/?v=1&ticket=a%20b%26c");
  });

  it("passes incoming messages to the app", async () => {
    const { socket, messages } = setup();
    socket.connect(); await flush(); last().serverOpens();
    last().serverSends('{"type":"pong"}');
    expect(messages).toEqual(['{"type":"pong"}']);
  });

  it("send() works only while open and never queues", async () => {
    const { socket } = setup();
    expect(socket.send("x")).toBe(false);
    socket.connect(); await flush();
    expect(socket.send("x")).toBe(false); // connecting, not open yet
    last().serverOpens();
    expect(socket.send("hello")).toBe(true);
    expect(last().sent).toEqual(["hello"]);
  });

  it("calling connect() twice (React StrictMode) opens one socket", async () => {
    const { socket } = setup();
    socket.connect(); socket.connect(); await flush();
    expect(FakeSocket.all).toHaveLength(1);
  });

  it("connect, disconnect, connect again leaves exactly one live socket", async () => {
    const { socket } = setup();
    socket.connect();
    socket.disconnect(); // the first ticket request is still in flight
    socket.connect();
    await flush();
    expect(FakeSocket.all).toHaveLength(1);
    last().serverOpens();
    expect(socket.currentStatus).toBe("open");
  });

  it("disconnect() while a ticket is pending never opens a socket", async () => {
    const { socket } = setup();
    socket.connect();
    socket.disconnect();
    await flush();
    expect(FakeSocket.all).toHaveLength(0);
    expect(socket.currentStatus).toBe("closed");
  });
});

describe("ReconnectingSocket: reconnecting", () => {
  it("reconnects with a NEW ticket after an unexpected close", async () => {
    const { socket, clock, ticketsIssued } = setup();
    socket.connect(); await flush(); last().serverOpens();
    last().serverCloses(1006);
    expect(socket.currentStatus).toBe("reconnecting");
    await clock.advance(499);
    expect(FakeSocket.all).toHaveLength(1); // not yet
    await clock.advance(1);
    expect(FakeSocket.all).toHaveLength(2);
    expect(last().url).toContain("ticket-2");
    expect(ticketsIssued()).toBe(2);
  });

  it("waits longer after each failed attempt", async () => {
    const { socket, clock } = setup();
    socket.connect(); await flush();
    const waits: number[] = [];
    for (let i = 0; i < 4; i++) {
      last().serverCloses(1006); // never opened: counts as a failure
      const before = FakeSocket.all.length;
      let waited = 0;
      while (FakeSocket.all.length === before) { await clock.advance(1); waited++; }
      waits.push(waited);
    }
    expect(waits).toEqual([500, 1000, 2000, 4000]);
  });

  it("starts over from the short delay only after the connection proved stable", async () => {
    const { socket, clock } = setup();
    socket.connect(); await flush(); last().serverOpens();
    await clock.advance(10_000); // stable: attempt counter resets
    last().serverCloses(1006);
    await clock.advance(499);
    expect(FakeSocket.all).toHaveLength(1);
    await clock.advance(1);
    expect(FakeSocket.all).toHaveLength(2);
  });

  it("does NOT reset the delay when a connection opens then drops at once", async () => {
    const { socket, clock } = setup();
    socket.connect(); await flush(); last().serverOpens();
    last().serverCloses(1012);         // flapping server: opened, then closed within 10 s
    await clock.advance(500); await flush(); last().serverOpens();
    last().serverCloses(1012);
    await clock.advance(999);
    expect(FakeSocket.all).toHaveLength(2); // second wait is 1000 ms, not 500
    await clock.advance(1);
    expect(FakeSocket.all).toHaveLength(3);
  });

  it("retries when the ticket request fails for an ordinary reason", async () => {
    let calls = 0;
    const { socket, clock } = setup({
      getTicket: async () => { if (++calls === 1) throw new Error("network"); return "ok"; },
    });
    socket.connect(); await flush();
    expect(FakeSocket.all).toHaveLength(0);
    expect(socket.currentStatus).toBe("reconnecting");
    await clock.advance(500);
    expect(last().url).toContain("ticket=ok");
  });

  it("stops for good on FatalSocketError (for example: logged out)", async () => {
    const { socket, clock } = setup({ getTicket: async () => { throw new FatalSocketError("401"); } });
    socket.connect(); await flush();
    expect(socket.currentStatus).toBe("closed");
    await clock.advance(60_000);
    expect(FakeSocket.all).toHaveLength(0);
  });

  it("stops for good on a fatal close code (4403 forbidden)", async () => {
    const { socket, clock } = setup();
    socket.connect(); await flush(); last().serverOpens();
    last().serverCloses(4403);
    expect(socket.currentStatus).toBe("closed");
    await clock.advance(60_000);
    expect(FakeSocket.all).toHaveLength(1);
  });

  it("treats an error before the socket opened as a lost connection", async () => {
    const { socket, clock } = setup();
    socket.connect(); await flush();
    const refused = last();
    refused.serverErrors();          // some runtimes send "error" and never "close"
    expect(socket.currentStatus).toBe("reconnecting");
    refused.serverCloses(1006);      // browsers do send it: it must not schedule a second retry
    await clock.advance(500); await flush();
    expect(FakeSocket.all).toHaveLength(2);
    await clock.advance(5_000);
    expect(FakeSocket.all).toHaveLength(2); // still two: only one retry was scheduled
  });

  it("an error on a socket that is open waits for the close event", async () => {
    const { socket } = setup();
    socket.connect(); await flush(); last().serverOpens();
    last().serverErrors();
    expect(socket.currentStatus).toBe("open");
    last().serverCloses(1006);
    expect(socket.currentStatus).toBe("reconnecting");
  });

  it("nudge() during the wait reconnects immediately", async () => {
    const { socket } = setup();
    socket.connect(); await flush(); last().serverOpens();
    last().serverCloses(1006);
    socket.nudge(); await flush();
    expect(FakeSocket.all).toHaveLength(2);
  });

  it("ignores late events from a socket it has already replaced", async () => {
    const { socket, clock, messages } = setup();
    socket.connect(); await flush(); last().serverOpens();
    const old = last();
    old.serverCloses(1006);
    await clock.advance(500); await flush(); last().serverOpens();
    old.serverSends("ghost"); // a delayed packet from the dead connection
    old.serverCloses(1006);   // and a duplicate close event
    expect(messages).toEqual([]);
    expect(socket.currentStatus).toBe("open");
  });

  it("disconnect() closes normally and never reconnects", async () => {
    const { socket, clock } = setup();
    socket.connect(); await flush(); last().serverOpens();
    const ws = last();
    socket.disconnect();
    expect(ws.closedWith).toBe(1000);
    await clock.advance(60_000);
    expect(FakeSocket.all).toHaveLength(1);
    expect(socket.currentStatus).toBe("closed");
  });
});

describe("ReconnectingSocket: heartbeat", () => {
  it("pings on a schedule and stays connected while the server answers", async () => {
    const { socket, clock } = setup();
    socket.connect(); await flush(); last().serverOpens();
    await clock.advance(25_000);
    expect(last().sent).toEqual(['{"type":"ping"}']);
    last().serverSends('{"type":"pong"}');
    await clock.advance(10_000);
    expect(socket.currentStatus).toBe("open");
  });

  it("gives up on a connection that goes silent and reconnects", async () => {
    const { socket, clock } = setup();
    socket.connect(); await flush(); last().serverOpens();
    const dead = last();
    await clock.advance(25_000);   // ping sent, no answer
    await clock.advance(10_000);   // pong timeout
    expect(socket.currentStatus).toBe("reconnecting");
    expect(dead.closedWith).toBe(4000);
    await clock.advance(500);
    expect(FakeSocket.all).toHaveLength(2);
  });

  it("nudge() on an open connection checks it now", async () => {
    const { socket, clock } = setup();
    socket.connect(); await flush(); last().serverOpens();
    socket.nudge();
    expect(last().sent).toEqual(['{"type":"ping"}']);
    await clock.advance(10_000);
    expect(socket.currentStatus).toBe("reconnecting");
  });
});
