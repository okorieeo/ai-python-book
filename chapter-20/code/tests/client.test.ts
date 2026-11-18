import assert from "node:assert/strict";
import { test } from "node:test";
import { createApiClient } from "../lib/api/client";
import { createEndpoints } from "../lib/api/endpoints";
import { ApiError } from "../lib/api/errors";

type Call = { url: string; init: RequestInit };

function fakeFetch(handler: (url: string, init: RequestInit) => Response | Promise<Response>) {
  const calls: Call[] = [];
  const fetchFn: typeof fetch = async (input, init = {}) => {
    calls.push({ url: String(input), init });
    return handler(String(input), init);
  };
  return { fetchFn, calls };
}
const json = (data: unknown, status = 200, headers: Record<string, string> = {}) =>
  new Response(JSON.stringify(data), { status, headers: { "content-type": "application/json", ...headers } });

test("GET builds the URL, sends JSON headers and parses the answer", async () => {
  const { fetchFn, calls } = fakeFetch(() => json({ results: [], next: null }));
  const api = createApiClient({ fetchFn });
  const page = await createEndpoints(api).listConversations({ limit: 5, cursor: "abc" });
  assert.deepEqual(page, { results: [], next: null });
  assert.equal(calls[0].url, "/api/v1/conversations?limit=5&cursor=abc");
  assert.equal(calls[0].init.credentials, "same-origin");
  assert.equal((calls[0].init.headers as Record<string, string>).Accept, "application/json");
});

test("POST sends a JSON body and the idempotency key", async () => {
  const { fetchFn, calls } = fakeFetch(() => json({ id: "cnv_1", title: "Hi", created_at: "x" }, 201));
  const created = await createEndpoints(createApiClient({ fetchFn })).createConversation("Hi", "key-123");
  assert.equal(created.id, "cnv_1");
  const headers = calls[0].init.headers as Record<string, string>;
  assert.equal(headers["Content-Type"], "application/json");
  assert.equal(headers["Idempotency-Key"], "key-123");
  assert.equal(calls[0].init.body, JSON.stringify({ title: "Hi" }));
});

test("error responses become ApiError with code, details and request id", async () => {
  const { fetchFn } = fakeFetch(() => json({ error: { code: "validation_error", message: "Bad", details: { title: ["Required."] } }, request_id: "req_9" }, 400));
  await assert.rejects(createApiClient({ fetchFn }).get("/x"), (error: unknown) => {
    assert.ok(error instanceof ApiError);
    assert.deepEqual([error.status, error.code, error.requestId, error.details], [400, "validation_error", "req_9", { title: ["Required."] }]);
    return true;
  });
});

test("204 returns undefined", async () => {
  const { fetchFn } = fakeFetch(() => new Response(null, { status: 204 }));
  assert.equal(await createApiClient({ fetchFn }).delete("/x"), undefined);
});

test("network failures become network_error", async () => {
  const fetchFn: typeof fetch = async () => { throw new TypeError("fetch failed"); };
  await assert.rejects(createApiClient({ fetchFn }).get("/x"), (e: unknown) => e instanceof ApiError && e.code === "network_error" && e.status === 0);
});

test("a slow server becomes a timeout error", async () => {
  const fetchFn: typeof fetch = (_input, init) => new Promise((_resolve, reject) => {
    init?.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
  });
  await assert.rejects(createApiClient({ fetchFn }).get("/slow", { timeoutMs: 40 }), (e: unknown) => e instanceof ApiError && e.code === "timeout");
});

test("a caller's cancellation is passed through, not reported as a network error", async () => {
  const fetchFn: typeof fetch = (_input, init) => new Promise((_resolve, reject) => {
    init?.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
  });
  const controller = new AbortController();
  const pending = createApiClient({ fetchFn }).get("/slow", { signal: controller.signal });
  controller.abort();
  await assert.rejects(pending, (e: unknown) => e instanceof DOMException && e.name === "AbortError");
});

test("session_expired triggers the app's handler once per failed call", async () => {
  let expired = 0;
  const { fetchFn } = fakeFetch(() => json({ error: { code: "session_expired", message: "Expired" }, request_id: "r" }, 401));
  const api = createApiClient({ fetchFn, onSessionExpired: () => { expired += 1; } });
  await assert.rejects(api.get("/me"));
  assert.equal(expired, 1);
});

test("retry-after is captured on rate limits", async () => {
  const { fetchFn } = fakeFetch(() => json({ error: { code: "rate_limited", message: "Slow down" }, request_id: "r" }, 429, { "retry-after": "12" }));
  await assert.rejects(createApiClient({ fetchFn }).get("/x"), (e: unknown) => e instanceof ApiError && e.retryAfter === 12);
});

test("ids are URL-encoded in paths", async () => {
  const { fetchFn, calls } = fakeFetch(() => json({ id: "a/b", title: "t", created_at: "x" }));
  await createEndpoints(createApiClient({ fetchFn })).getConversation("a/b?x=1");
  assert.equal(calls[0].url, "/api/v1/conversations/a%2Fb%3Fx%3D1");
});
