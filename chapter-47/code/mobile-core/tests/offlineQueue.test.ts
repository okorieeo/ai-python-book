import { ApiError, NetworkError, QueueFullError, SessionExpiredError } from "../src/errors";
import { OfflineQueue, RequestSender } from "../src/offlineQueue";
import { MemoryStore } from "../src/storage";
import { flushPromises } from "./helpers";

interface Sent { method: string; path: string; body?: unknown; idempotencyKey?: string }

/** A client double: each call consumes the next outcome ("ok" or an error to throw). */
function fakeClient(outcomes: Array<"ok" | Error> = []) {
  const sent: Sent[] = [];
  const client: RequestSender = {
    request: async (method, path, opts) => {
      sent.push({ method, path, body: opts?.body, idempotencyKey: opts?.idempotencyKey });
      const next = outcomes.shift() ?? "ok";
      if (next !== "ok") throw next;
      return undefined as never;
    },
  };
  return { client, sent };
}

function make(outcomes: Array<"ok" | Error> = [], extra: Partial<ConstructorParameters<typeof OfflineQueue>[0]> = {}) {
  const storage = new MemoryStore();
  const { client, sent } = fakeClient(outcomes);
  let t = 1000;
  let n = 0;
  const queue = new OfflineQueue({ storage, client, now: () => t++, makeId: () => `id${++n}`, ...extra });
  return { queue, storage, sent };
}

const post = (path: string, body: unknown = {}, extra = {}) => ({ method: "POST" as const, path, body, ...extra });

test("items are saved to storage as soon as they are queued", async () => {
  const { queue, storage } = make();
  await queue.enqueue(post("/notes/", { text: "hi" }));
  const saved = JSON.parse(storage.data.get("offline.queue.v1")!);
  expect(saved.v).toBe(1);
  expect(saved.items[0]).toMatchObject({ id: "id1", path: "/notes/", status: "pending", idempotencyKey: "idem_id1" });
});

test("queued items survive the app being closed and reopened", async () => {
  const { queue, storage } = make();
  await queue.enqueue(post("/a/"));
  await queue.enqueue(post("/b/"));
  const reopened = new OfflineQueue({ storage, client: fakeClient().client });
  await reopened.load();
  expect(reopened.pending().map((i) => i.path)).toEqual(["/a/", "/b/"]);
});

test("flush sends in order, with idempotency keys, and empties the queue", async () => {
  const { queue, sent } = make();
  await queue.enqueue(post("/a/", { n: 1 }));
  await queue.enqueue(post("/b/", { n: 2 }));
  const result = await queue.flush();
  expect(result).toEqual({ sent: 2, failed: 0, remaining: 0, stoppedBecause: "done" });
  expect(sent.map((s) => [s.path, s.idempotencyKey])).toEqual([["/a/", "idem_id1"], ["/b/", "idem_id2"]]);
  expect(queue.pending()).toHaveLength(0);
});

test("the same item keeps the same idempotency key on every attempt", async () => {
  const { queue, sent } = make([new NetworkError(), "ok"]);
  await queue.enqueue(post("/a/"));
  await queue.flush(); // fails, stays queued
  await queue.flush(); // succeeds
  expect(sent.map((s) => s.idempotencyKey)).toEqual(["idem_id1", "idem_id1"]);
});

test("a network failure stops the run and keeps the order", async () => {
  const { queue, sent } = make([new NetworkError()]);
  await queue.enqueue(post("/a/"));
  await queue.enqueue(post("/b/"));
  const result = await queue.flush();
  expect(result).toMatchObject({ sent: 0, remaining: 2, stoppedBecause: "network" });
  expect(sent).toHaveLength(1); // /b/ was not tried: /a/ must go first
  expect(queue.pending().map((i) => i.attempts)).toEqual([1, 0]);
});

test("after too many failed attempts an item is parked as failed", async () => {
  const { queue } = make([new NetworkError(), new NetworkError(), new NetworkError()], { maxAttempts: 3 });
  const item = await queue.enqueue(post("/a/"));
  await queue.flush();
  await queue.flush();
  const last = await queue.flush();
  expect(last.failed).toBe(1);
  expect(queue.failed()[0]).toMatchObject({ id: item.id, attempts: 3, lastError: { code: "NetworkError" } });
});

test("a refusal from the server is parked, and the rest of the queue still goes", async () => {
  const { queue, sent } = make([new ApiError(422, "invalid", "Title is required"), "ok"]);
  await queue.enqueue(post("/bad/"));
  await queue.enqueue(post("/good/"));
  const result = await queue.flush();
  expect(result).toMatchObject({ sent: 1, failed: 1, remaining: 0, stoppedBecause: "done" });
  expect(sent).toHaveLength(2);
  expect(queue.failed()[0]!.lastError).toEqual({ status: 422, code: "invalid", message: "Title is required" });
});

test("a server that is busy is retried later, not parked", async () => {
  const { queue } = make([new ApiError(503, "http_503", "busy")]);
  await queue.enqueue(post("/a/"));
  const result = await queue.flush();
  expect(result.stoppedBecause).toBe("network");
  expect(queue.pending()).toHaveLength(1);
});

test("being signed out keeps everything for after the next sign-in", async () => {
  const { queue } = make([new SessionExpiredError()]);
  await queue.enqueue(post("/a/"));
  await queue.enqueue(post("/b/"));
  const result = await queue.flush();
  expect(result.stoppedBecause).toBe("signed-out");
  expect(queue.pending()).toHaveLength(2);
  expect(queue.failed()).toHaveLength(0);
});

test("nothing is sent while offline", async () => {
  const { queue, sent } = make([], { isOnline: () => false });
  await queue.enqueue(post("/a/"));
  expect(await queue.flush()).toMatchObject({ sent: 0, remaining: 1, stoppedBecause: "offline" });
  expect(sent).toHaveLength(0);
});

test("overlapping flushes share one run, so nothing is sent twice", async () => {
  const { queue, sent } = make();
  await queue.enqueue(post("/a/"));
  const [r1, r2] = await Promise.all([queue.flush(), queue.flush(), queue.flush()]);
  expect(r1).toBe(r2);
  expect(sent).toHaveLength(1);
});

test("a newer item with the same dedupeKey replaces the one still waiting", async () => {
  const { queue, sent } = make();
  await queue.enqueue(post("/c/1/rename/", { title: "First" }, { dedupeKey: "rename:1" }));
  await queue.enqueue(post("/c/1/rename/", { title: "Second" }, { dedupeKey: "rename:1" }));
  await queue.enqueue(post("/c/2/rename/", { title: "Other" }, { dedupeKey: "rename:2" }));
  await queue.flush();
  expect(sent.map((s) => (s.body as { title: string }).title)).toEqual(["Second", "Other"]);
});

test("an item being sent right now is never replaced", async () => {
  const storage = new MemoryStore();
  let release!: () => void;
  const gate = new Promise<void>((r) => (release = r));
  const sent: string[] = [];
  const queue = new OfflineQueue({
    storage, makeId: (() => { let n = 0; return () => `id${++n}`; })(),
    client: { request: async (_m, _p, opts) => { sent.push((opts!.body as { v: string }).v); await gate; return undefined as never; } },
  });
  await queue.enqueue(post("/x/", { v: "old" }, { dedupeKey: "k" }));
  const running = queue.flush();
  await flushPromises();
  await queue.enqueue(post("/x/", { v: "new" }, { dedupeKey: "k" })); // while "old" is on the wire
  release();
  await running;
  await queue.flush();
  expect(sent).toEqual(["old", "new"]); // both go: the first was already in flight
});

test("the queue has a size limit", async () => {
  const { queue } = make([], { maxItems: 2 });
  await queue.enqueue(post("/1/"));
  await queue.enqueue(post("/2/"));
  await expect(queue.enqueue(post("/3/"))).rejects.toBeInstanceOf(QueueFullError);
});

test("unreadable saved data starts an empty queue and says so", async () => {
  const storage = new MemoryStore();
  storage.data.set("offline.queue.v1", "{not json");
  const onCorrupt = jest.fn();
  const queue = new OfflineQueue({ storage, client: fakeClient().client, onCorrupt });
  await queue.load();
  expect(queue.pending()).toEqual([]);
  expect(onCorrupt).toHaveBeenCalledTimes(1);
  for (const bad of [JSON.stringify({ v: 2, items: [] }), JSON.stringify({ v: 1, items: [{ id: 1 }] })]) {
    storage.data.set("offline.queue.v1", bad);
    const q = new OfflineQueue({ storage, client: fakeClient().client, onCorrupt });
    await q.load();
    expect(q.pending()).toEqual([]);
  }
});

test("a failed item can be retried or discarded by the user", async () => {
  const { queue } = make([new ApiError(409, "conflict", "Already exists"), "ok"]);
  const item = await queue.enqueue(post("/a/"));
  await queue.flush();
  expect(queue.failed()).toHaveLength(1);
  await queue.retry(item.id);
  expect(queue.pending()[0]).toMatchObject({ attempts: 0, status: "pending" });
  await queue.flush();
  expect(queue.pending()).toHaveLength(0);
  const second = await queue.enqueue(post("/b/"));
  await queue.discard(second.id);
  expect(queue.pending()).toHaveLength(0);
});

test("listeners hear about every change, so a badge can update", async () => {
  const { queue } = make();
  const listener = jest.fn();
  const off = queue.subscribe(listener);
  await queue.enqueue(post("/a/"));
  await queue.flush();
  expect(listener.mock.calls.length).toBeGreaterThanOrEqual(2);
  off();
  const before = listener.mock.calls.length;
  await queue.enqueue(post("/b/"));
  expect(listener.mock.calls.length).toBe(before);
});
