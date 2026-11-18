# Chapter 20 — Connecting Next.js to Django: extended material

The printed edition of *Building AI-Powered Apps* keeps each chapter short. This file holds the longer material that was moved here so that nothing is lost: the full hands-on lab, troubleshooting tables, checklists, further exercises, and sections that were condensed for print.


---

# Sections condensed for print


## The API Contract in TypeScript › Design notes

- **The UI switches on** `code`**, never on** `message`**.** Codes are stable; messages are for developers. `messageForError` turns a code into friendly, translatable text, and unknown server errors in the 500 range always show a generic message so internals never leak to users.
- **Two synthetic codes** exist only on the client: `network_error` (no response at all) and `timeout`. Both have `status: 0`.
- `isRetryable` **is deliberately strict:** only network errors, timeouts and 502, 503 and 504. Never retry a `400`, `401`, `403`, `404` or `409`: repeating it cannot succeed and may do harm.
- **The class avoids constructor parameter properties** (`constructor(public status: number)`), so the file runs under plain Node type-stripping as well as in the bundler. That is why the tests need no build step.

## The Browser API Client › Testing the client with a fake fetch

Because the client takes `fetchFn` as a parameter, tests pass a fake that returns canned responses and records the calls. Ten tests cover URLs, headers, bodies, error parsing, `204`, network failure, timeouts, cancellation, session expiry, `Retry-After` and URL encoding:

**tests/client.test.ts**

```
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
```


## JWT Basics for the Frontend

In this design the browser never sees a token, but the **server side of the gateway** needs to know when the access token is about to expire, so it can refresh before the backend says no. A JWT is three base64url-encoded parts separated by dots (header, payload, signature); the payload contains claims such as `exp` (expiry, in seconds since 1970).

**lib/auth/jwt.ts**

```
/** Read the contents of a JWT WITHOUT verifying it. Only the server can verify; we only need to know when it expires. */
export function decodeJwtPayload(token: string): Record<string, unknown> | null {
  const parts = token.split(".");
  if (parts.length !== 3) return null;
  try {
    const base64 = parts[1].replace(/-/g, "+").replace(/_/g, "/");
    const binary = atob(base64 + "=".repeat((4 - (base64.length % 4)) % 4));
    const bytes = Uint8Array.from(binary, (char) => char.charCodeAt(0));
    const payload: unknown = JSON.parse(new TextDecoder().decode(bytes));
    return typeof payload === "object" && payload !== null && !Array.isArray(payload) ? (payload as Record<string, unknown>) : null;
  } catch {
    return null;
  }
}

/** Expiry as seconds since the epoch, or null if the token is unreadable or has no `exp`. */
export function tokenExpiresAt(token: string): number | null {
  const exp = decodeJwtPayload(token)?.exp;
  return typeof exp === "number" ? exp : null;
}

/** True if the token is missing, unreadable, expired, or will expire within `skewSeconds`. */
export function isExpiringSoon(token: string | undefined, nowSeconds: number, skewSeconds = 30): boolean {
  if (!token) return true;
  const exp = tokenExpiresAt(token);
  return exp === null || exp - skewSeconds <= nowSeconds;
}
```

> **Decoding is not verifying**
>
> These helpers **read** a token; they do not prove it is genuine. Only the backend, which holds the signing secret, can verify a signature. The gateway uses `exp` purely as a hint to avoid a pointless round trip. If the hint is wrong (a tampered token), the backend answers `401` and the gateway refreshes once and retries, as the tests demonstrate. **Never make an authorization decision from a decoded token on the client.**

The helper also decodes the payload as UTF-8 properly (a token containing a name such as "Zoë" would otherwise be corrupted by plain `atob`), and every malformed input returns `null` instead of throwing.


## The Gateway: A Backend-for-Frontend in 200 Lines › Reading the gateway, step by step

| **Step** | **What and why** |
|---|---|
| **Method and path checks** | Only GET, POST, PUT, PATCH and DELETE. Path segments may not be empty, `.`, `..` or contain slashes: this stops tricks such as `..%2Fadmin` that would escape `/api/v1/` |
| **CSRF defence** | For unsafe methods, `Sec-Fetch-Site` must be `same-origin` or `none`; if that header is absent, `Origin` must match the app. Non-browser callers send neither, so curl and tests work. Safe GETs are not blocked |
| **Path classification** | `auth/register` and the email and password-reset endpoints are public (no token, none attached). Anything else under `auth/` returns `404`. All other paths are private |
| **Token preparation** | No cookies at all: `401 not_authenticated`. Missing or soon-to-expire access token: refresh first |
| **Forwarding** | Only allowlisted request headers go to Django; the Bearer token and a request id are added. The body is read once (these are small JSON bodies; uploads use pre-signed URLs) |
| **Retry once** | If Django answers `401` to a token we believed was fine (revoked, key rotated), refresh once and retry once. Never loop |
| **Answering** | Status and body pass through; only allowlisted response headers return; new cookies are appended. `204` and `304` have no body. SSE streams pass straight through without buffering |
| **Failure handling** | Backend unreachable: `502` and **keep** the session. Timeout: `504`. Refresh rejected by the backend: `401 session_expired` and **clear** the cookies |


## The Gateway: A Backend-for-Frontend in 200 Lines › Proof: 30 integration tests against a real HTTP backend

These tests start the Python mock backend (access tokens that live **2 seconds**, so expiry is real, not simulated) and call the handlers and the gateway as ordinary functions with `Request` objects. They cover login, logout, header filtering, idempotency, CSRF, path tricks, public and blocked endpoints, refresh, concurrency, tampered tokens, revoked sessions, token-reuse detection, upstream failures, timeouts and streaming:

**tests/helpers.ts**

```
import { spawn } from "node:child_process";

/** Start the Python mock backend on a port and wait until it is listening. */
export async function startMock(port: number, env: Record<string, string> = {}): Promise<{ stop: () => void }> {
  const script = new URL("../../tools/mock_backend/mock_backend.py", import.meta.url).pathname;
  const child = spawn("python3", [script], { env: { ...process.env, PORT: String(port), ...env }, stdio: ["ignore", "pipe", "inherit"] });
  await new Promise<void>((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("mock backend did not start")), 8000);
    child.stdout!.on("data", (chunk: Buffer) => {
      if (String(chunk).includes("Mock backend")) {
        clearTimeout(timer);
        resolve();
      }
    });
    child.on("error", reject);
  });
  return { stop: () => child.kill() };
}

export const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));
```

**tests/bff.test.ts**

```
import assert from "node:assert/strict";
import { after, before, beforeEach, describe, test } from "node:test";
import { handleLogin, handleLogout } from "../lib/bff/auth-handlers";
import { backendRefresh } from "../lib/bff/backend";
import type { BffConfig } from "../lib/bff/config";
import { forwardToBackend } from "../lib/bff/gateway";
import { sleep, startMock } from "./helpers";

const PORT = 8211;
const config: BffConfig = { backendUrl: `http://127.0.0.1:${PORT}`, secureCookies: false, accessSkewSeconds: 0 };
let mock: { stop: () => void };

before(async () => { mock = await startMock(PORT, { ACCESS_TTL: "2" }); });
after(() => mock.stop());
beforeEach(async () => { await fetch(`${config.backendUrl}/api/v1/_debug/reset`, { method: "POST" }); });

const stats = async () => (await (await fetch(`${config.backendUrl}/api/v1/_debug/stats`)).json()) as { login_calls: number; refresh_calls: number };

function loginRequest(body: unknown, headers: Record<string, string> = {}) {
  return new Request("http://app.test/api/auth/login", { method: "POST", headers: { "content-type": "application/json", ...headers }, body: JSON.stringify(body) });
}
const ADA = { email: "ada@example.com", password: "correct-horse-battery" };

/** Log in through the real handler and collect the cookies the browser would store. */
async function login(cfg: BffConfig = config) {
  const response = await handleLogin(loginRequest(ADA), cfg);
  assert.equal(response.status, 200);
  const jar: Record<string, string> = {};
  for (const line of response.headers.getSetCookie()) {
    const [pair] = line.split(";");
    const index = pair.indexOf("=");
    jar[pair.slice(0, index)] = pair.slice(index + 1);
  }
  return { jar, header: Object.entries(jar).map(([k, v]) => `${k}=${v}`).join("; ") };
}

function call(path: string, init: { method?: string; cookie?: string; headers?: Record<string, string>; body?: unknown; cfg?: BffConfig } = {}) {
  const url = new URL(`http://app.test/api/v1/${path}`);
  const headers = new Headers(init.headers);
  if (init.cookie) headers.set("cookie", init.cookie);
  if (init.body !== undefined) headers.set("content-type", "application/json");
  const request = new Request(url, { method: init.method ?? "GET", headers, body: init.body === undefined ? undefined : JSON.stringify(init.body) });
  return forwardToBackend(request, url.pathname.replace("/api/v1/", "").split("/").map(decodeURIComponent), init.cfg ?? config);
}

describe("login and logout handlers", () => {
  test("login sets two HttpOnly cookies and returns only the user", async () => {
    const response = await handleLogin(loginRequest(ADA), config);
    const body = await response.json();
    assert.equal(response.status, 200);
    assert.deepEqual(Object.keys(body), ["user"]);
    assert.equal(body.user.email, "ada@example.com");
    assert.equal(response.headers.get("cache-control"), "no-store");
    const cookies = response.headers.getSetCookie();
    assert.equal(cookies.length, 2);
    for (const cookie of cookies) {
      assert.match(cookie, /; HttpOnly/);
      assert.match(cookie, /; SameSite=Lax/);
      assert.match(cookie, /; Path=\//);
      assert.doesNotMatch(cookie, /; Secure/);
    }
    assert.match(cookies[0], /^ai_access=/);
    assert.match(cookies[1], /^ai_refresh=/);
    assert.match(cookies[0], /Max-Age=[12];?/);                       // the 2-second access token
  });

  test("production cookies are Secure", async () => {
    const response = await handleLogin(loginRequest(ADA), { ...config, secureCookies: true });
    assert.ok(response.headers.getSetCookie().every((c) => c.endsWith("; Secure")));
  });

  test("wrong password: the backend's error comes through and no cookies are set", async () => {
    const response = await handleLogin(loginRequest({ email: "ada@example.com", password: "wrong" }), config);
    const body = await response.json();
    assert.equal(response.status, 401);
    assert.equal(body.error.code, "authentication_failed");
    assert.equal(response.headers.getSetCookie().length, 0);
  });

  test("missing fields are rejected before the backend is called", async () => {
    const response = await handleLogin(loginRequest({ email: "ada@example.com" }), config);
    const body = await response.json();
    assert.equal(response.status, 400);
    assert.deepEqual(Object.keys(body.error.details), ["password"]);
    assert.equal((await stats()).login_calls, 0);
  });

  test("invalid JSON and cross-site logins are refused", async () => {
    const bad = await handleLogin(new Request("http://app.test/api/auth/login", { method: "POST", body: "{nope" }), config);
    assert.equal(bad.status, 400);
    const cross = await handleLogin(loginRequest(ADA, { origin: "https://evil.example" }), config);
    assert.equal(cross.status, 403);
    assert.equal((await cross.json()).error.code, "csrf_blocked");
  });

  test("backend down gives a clean 502", async () => {
    const response = await handleLogin(loginRequest(ADA), { ...config, backendUrl: "http://127.0.0.1:1" });
    assert.equal(response.status, 502);
    assert.equal((await response.json()).error.code, "upstream_unavailable");
  });

  test("logout clears cookies and revokes the session on the backend", async () => {
    const { jar, header } = await login();
    const response = await handleLogout(new Request("http://app.test/api/auth/logout", { method: "POST", headers: { cookie: header } }), config);
    assert.equal(response.status, 204);
    const cookies = response.headers.getSetCookie();
    assert.equal(cookies.length, 2);
    assert.ok(cookies.every((c) => /Max-Age=0/.test(c)));
    await assert.rejects(backendRefresh(config, decodeURIComponent(jar.ai_refresh), "req_test0001"), /./);   // the old refresh token is dead
  });

  test("logout works even when the backend is down", async () => {
    const { header } = await login();
    const response = await handleLogout(new Request("http://app.test/api/auth/logout", { method: "POST", headers: { cookie: header } }), { ...config, backendUrl: "http://127.0.0.1:1" });
    assert.equal(response.status, 204);
    assert.equal(response.headers.getSetCookie().length, 2);
  });
});

describe("gateway basics", () => {
  test("no cookies means 401 and the backend is never called", async () => {
    const response = await call("conversations");
    assert.equal(response.status, 401);
    assert.equal((await response.json()).error.code, "not_authenticated");
  });

  test("an authenticated GET returns the backend's data, and the request id is propagated", async () => {
    const { header } = await login();
    const response = await call("conversations?limit=3", { cookie: header, headers: { "x-request-id": "req_abcdef123456" } });
    const body = await response.json();
    assert.equal(response.status, 200);
    assert.equal(body.results.length, 3);
    assert.ok(body.next);
    assert.equal(response.headers.get("x-request-id"), "req_abcdef123456");
    assert.equal((await stats()).refresh_calls, 0);                  // a fresh token needs no refresh
  });

  test("the backend sees a Bearer token and NOTHING the browser should not control", async () => {
    const { header } = await login();
    const response = await call("_debug/headers", { cookie: header, headers: {
      authorization: "Bearer attacker-token", "x-forwarded-for": "6.6.6.6", "x-custom": "nope", "idempotency-key": "key-1", "accept-language": "en",
    } });
    const seen = await response.json();
    assert.match(seen.authorization, /^Bearer eyJ/);
    assert.notEqual(seen.authorization, "Bearer attacker-token");
    assert.equal(seen.cookie, undefined);
    assert.equal(seen["x-forwarded-for"], undefined);
    assert.equal(seen["x-custom"], undefined);
    assert.equal(seen["idempotency-key"], "key-1");
    assert.equal(seen["accept-language"], "en");
  });

  test("response headers are filtered", async () => {
    const { header } = await login();
    const response = await call("conversations", { cookie: header });
    assert.equal(response.headers.get("server"), null);
    assert.equal(response.headers.get("date"), null);
    assert.match(response.headers.get("content-type") ?? "", /json/);
  });

  test("idempotent creation works through the gateway", async () => {
    const { header } = await login();
    const make = () => call("conversations", { method: "POST", cookie: header, headers: { "idempotency-key": "k-42" }, body: { title: "Once only" } });
    const first = await make();
    const second = await make();
    assert.equal(first.status, 201);
    assert.equal(second.headers.get("idempotent-replayed"), "true");
    assert.equal((await first.json()).id, (await second.json()).id);
  });

  test("validation errors from the backend are passed through unchanged", async () => {
    const { header } = await login();
    const response = await call("conversations", { method: "POST", cookie: header, body: { title: "" } });
    assert.equal(response.status, 400);
    assert.deepEqual(Object.keys((await response.json()).error.details), ["title"]);
  });

  test("upstream 404 and 500 are passed through", async () => {
    const { header } = await login();
    assert.equal((await call("conversations/nope", { cookie: header })).status, 404);
    assert.equal((await call("_debug/boom", { cookie: header })).status, 500);
  });
});

describe("what the gateway refuses", () => {
  test("token endpoints are not reachable through it", async () => {
    const { header } = await login();
    for (const path of ["auth/login", "auth/refresh", "auth/logout", "auth/social/google", "auth/anything"]) {
      const response = await call(path, { method: "POST", cookie: header, body: ADA });
      assert.equal(response.status, 404, path);
    }
  });

  test("public auth endpoints pass through without credentials", async () => {
    const created = await call("auth/register", { method: "POST", body: { email: "new@example.com", password: "a-long-password", name: "New" } });
    assert.equal(created.status, 201);
    const invalid = await call("auth/register", { method: "POST", body: { email: "ada@example.com", password: "x", name: "" } });
    assert.equal(invalid.status, 400);
    assert.deepEqual(Object.keys((await invalid.json()).error.details).sort(), ["email", "name", "password"]);
  });

  test("path tricks are rejected", async () => {
    const { header } = await login();
    for (const segments of [["..", "admin"], ["conversations", "..", "x"], ["a/b"], ["a\\b"], [""], []]) {
      const url = new URL("http://app.test/api/v1/x");
      const response = await forwardToBackend(new Request(url, { headers: { cookie: header } }), segments, config);
      assert.equal(response.status, 400, JSON.stringify(segments));
    }
  });

  test("unsupported methods", async () => {
    const response = await call("conversations", { method: "OPTIONS" });
    assert.equal(response.status, 405);
  });

  test("cross-site writes are blocked, same-site writes are allowed", async () => {
    const { header } = await login();
    const post = (headers: Record<string, string>) => call("conversations", { method: "POST", cookie: header, headers, body: { title: "CSRF test" } });
    assert.equal((await post({ "sec-fetch-site": "cross-site" })).status, 403);
    assert.equal((await post({ "sec-fetch-site": "same-site" })).status, 403);
    assert.equal((await post({ origin: "https://evil.example" })).status, 403);
    assert.equal((await post({ origin: "http://app.test" })).status, 201);
    assert.equal((await post({ "sec-fetch-site": "same-origin" })).status, 201);
    assert.equal((await post({})).status, 201);                                       // curl and server-side callers
    const readOnly = await call("conversations", { cookie: header, headers: { "sec-fetch-site": "cross-site" } });
    assert.equal(readOnly.status, 200);                                               // GET is safe; CORS stops other sites reading it
  });
});

describe("token refresh", () => {
  test("an expired access token is refreshed transparently and the new cookies are returned", async () => {
    const { header } = await login();
    await sleep(2300);                                                // the 2-second access token expires
    const response = await call("me", { cookie: header });
    assert.equal(response.status, 200);
    assert.equal((await response.json()).email, "ada@example.com");
    assert.equal((await stats()).refresh_calls, 1);
    const cookies = response.headers.getSetCookie();
    assert.equal(cookies.length, 2);
    assert.ok(cookies[0].startsWith("ai_access=") && cookies[1].startsWith("ai_refresh="));
    assert.notEqual(cookies[0].split(";")[0], header.split(";")[0].trim());     // a different access token than before
  });

  test("five simultaneous requests share ONE refresh", async () => {
    const { header } = await login();
    await sleep(2300);
    const responses = await Promise.all(Array.from({ length: 5 }, () => call("conversations?limit=2", { cookie: header })));
    assert.deepEqual(responses.map((r) => r.status), [200, 200, 200, 200, 200]);
    assert.equal((await stats()).refresh_calls, 1);
    const refreshCookies = new Set(responses.map((r) => r.headers.getSetCookie()[1].split(";")[0]));
    assert.equal(refreshCookies.size, 1);                              // every response carries the same new refresh token
  });

  test("a token the backend rejects triggers one refresh and one retry", async () => {
    const { header } = await login();
    const tampered = header.replace(/(ai_access=[^;]+)(.)(;|$)/, (_m, token: string, _last: string, end: string) => `${token}X${end}`);
    assert.notEqual(tampered, header);
    const response = await call("me", { cookie: tampered });
    assert.equal(response.status, 200);
    assert.equal((await stats()).refresh_calls, 1);
    assert.equal(response.headers.getSetCookie().length, 2);
  });

  test("a revoked session ends with 401 session_expired and cleared cookies", async () => {
    const { header } = await login();
    await handleLogout(new Request("http://app.test/api/auth/logout", { method: "POST", headers: { cookie: header } }), config);
    const tampered = header.replace(/(ai_access=[^;]+)(.)(;|$)/, (_m, token: string, _l: string, end: string) => `${token}X${end}`);
    const response = await call("me", { cookie: tampered });
    assert.equal(response.status, 401);
    assert.equal((await response.json()).error.code, "session_expired");
    assert.ok(response.headers.getSetCookie().every((c) => /Max-Age=0/.test(c)));
  });

  test("replaying an already-used refresh token is treated as theft and ends the session", async () => {
    const { jar, header } = await login();
    await backendRefresh(config, decodeURIComponent(jar.ai_refresh), "req_thief0001");        // someone else rotates it first
    const tampered = header.replace(/(ai_access=[^;]+)(.)(;|$)/, (_m, token: string, _l: string, end: string) => `${token}X${end}`);
    const response = await call("me", { cookie: tampered });
    assert.equal(response.status, 401);
    assert.equal((await response.json()).error.code, "session_expired");
  });

  test("only a refresh cookie is enough to get back in", async () => {
    const { header } = await login();
    const refreshOnly = header.split("; ").filter((c) => c.startsWith("ai_refresh=")).join("; ");
    const response = await call("me", { cookie: refreshOnly });
    assert.equal(response.status, 200);
    assert.equal((await stats()).refresh_calls, 1);
  });
});

describe("failure modes and streaming", () => {
  test("backend down: 502, and the session is NOT cleared", async () => {
    const { header } = await login();
    const response = await call("conversations", { cookie: header, cfg: { ...config, backendUrl: "http://127.0.0.1:1" } });
    assert.equal(response.status, 502);
    assert.equal((await response.json()).error.code, "upstream_unavailable");
    assert.equal(response.headers.getSetCookie().length, 0);
  });

  test("backend down during a needed refresh also keeps the cookies", async () => {
    const { header } = await login();
    await sleep(2300);
    const response = await call("me", { cookie: header, cfg: { ...config, backendUrl: "http://127.0.0.1:1" } });
    assert.equal(response.status, 502);
    assert.equal(response.headers.getSetCookie().length, 0);
  });

  test("a slow backend times out with 504", async () => {
    const { header } = await login();
    const response = await call("_debug/slow?ms=1500", { cookie: header, cfg: { ...config, timeoutMs: 300 } });
    assert.equal(response.status, 504);
  });

  test("server-sent events stream through without buffering", async () => {
    const { header } = await login();
    const started = Date.now();
    const response = await call("_debug/stream", { cookie: header });
    assert.match(response.headers.get("content-type") ?? "", /text\/event-stream/);
    const reader = response.body!.getReader();
    const decoder = new TextDecoder();
    const first = await reader.read();
    const firstAt = Date.now() - started;
    let text = decoder.decode(first.value);
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      text += decoder.decode(value);
    }
    const totalAt = Date.now() - started;
    assert.equal((text.match(/event: tick/g) ?? []).length, 3);
    assert.ok(firstAt < 300, `first event took ${firstAt} ms`);
    assert.ok(totalAt > 450, `whole stream took only ${totalAt} ms`);
  });
});
```


## The Gateway: A Backend-for-Frontend in 200 Lines › The mock backend

The mock implements the contract from Chapters 8 and 13 with the Python standard library: HS256 tokens, rotation with **reuse detection** (replaying a used refresh token revokes the whole session), cursor pagination, idempotent creation, tickets, and a few debugging endpoints (header echo, call counters, a slow endpoint, a server-sent-events stream). Keep it in `tools/mock_backend/mock_backend.py`. Run it by hand to develop the frontend before the real backend exists:

**terminal**

```bash
python tools/mock_backend/mock_backend.py
# Mock backend on http://localhost:8000/api/v1  (login: ada@example.com / correct-horse-battery, access token lifetime 900s)

# short-lived access tokens, to watch refreshes happen:
PORT=8000 ACCESS_TTL=20 python tools/mock_backend/mock_backend.py
```

**tools/mock_backend/mock_backend.py**

```
"""A stand-in for the Django backend, implementing the auth and API contract from Chapters 8 and 13.

Standard library only. Use it to build and test the Next.js app before (or without) the real backend.

    python mock_backend.py                 # http://localhost:8000
    PORT=8100 ACCESS_TTL=3 python mock_backend.py       # short-lived access tokens, to watch refreshes happen
"""
import base64
import hashlib
import hmac
import json
import os
import re
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

PORT = int(os.environ.get("PORT", "8000"))
ACCESS_TTL = int(os.environ.get("ACCESS_TTL", "900"))              # seconds
REFRESH_TTL = int(os.environ.get("REFRESH_TTL", str(30 * 24 * 3600)))
SECRET = os.environ.get("MOCK_SECRET", "dev-only-secret").encode()
PREFIX = "/api/v1"
MAX_LIMIT = 50

USERS = {
    "ada@example.com": {"id": "usr_ada", "name": "Ada", "password": "correct-horse-battery"},
    "bo@example.com": {"id": "usr_bo", "name": "Bo", "password": "another-long-password"},
}
LOCK = threading.Lock()
STATS = {"login_calls": 0, "refresh_calls": 0}
REFRESH_TOKENS: dict[str, dict] = {}                                # jti -> {user, family, used}
REVOKED_FAMILIES: set[str] = set()
CONVERSATIONS: dict[str, list] = {}
IDEMPOTENT: dict[tuple, tuple] = {}

def seed():
    CONVERSATIONS.clear()
    CONVERSATIONS["usr_ada"] = [
        {"id": f"cnv_{i:03d}", "title": f"Conversation {i}", "created_at": f"2026-11-01T09:{i:02d}:00Z"}
        for i in range(7, 0, -1)
    ]
    CONVERSATIONS["usr_bo"] = []

# ----------------------------------------------------------------------------- tokens (HS256 JWT)
def b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

def unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))

def make_token(user_id: str, kind: str, ttl: int, family: str | None = None) -> tuple[str, str]:
    jti = uuid.uuid4().hex
    now = int(time.time())
    payload = {"sub": user_id, "type": kind, "jti": jti, "iat": now, "exp": now + ttl}
    if family:
        payload["fam"] = family
    head = b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    body = b64(json.dumps(payload).encode())
    sig = b64(hmac.new(SECRET, f"{head}.{body}".encode(), hashlib.sha256).digest())
    return f"{head}.{body}.{sig}", jti

class TokenError(Exception):
    def __init__(self, code: str):
        self.code = code

def read_token(token: str, kind: str) -> dict:
    try:
        head, body, sig = token.split(".")
        expected = b64(hmac.new(SECRET, f"{head}.{body}".encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expected):
            raise TokenError("token_invalid")
        payload = json.loads(unb64(body))
    except TokenError:
        raise
    except Exception:
        raise TokenError("token_invalid") from None
    if payload.get("type") != kind:
        raise TokenError("token_invalid")
    if payload["exp"] <= time.time():
        raise TokenError("token_expired")
    return payload

def issue_pair(user_id: str, family: str | None = None) -> dict:
    family = family or uuid.uuid4().hex
    access, _ = make_token(user_id, "access", ACCESS_TTL)
    refresh, jti = make_token(user_id, "refresh", REFRESH_TTL, family)
    REFRESH_TOKENS[jti] = {"user": user_id, "family": family, "used": False}
    return {"access": access, "refresh": refresh}

def encode_cursor(last_id: str) -> str:
    return base64.urlsafe_b64encode(json.dumps({"after": last_id}).encode()).decode()

class Handler(BaseHTTPRequestHandler):
    # ---------------------------------------------------------------- helpers
    def _send(self, status, payload=None, headers=None):
        body = b"" if payload is None else json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("X-Request-ID", self.request_id)
        if payload is not None:
            self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _error(self, status, code, message, details=None, headers=None):
        error = {"code": code, "message": message}
        if details:
            error["details"] = details
        self._send(status, {"error": error, "request_id": self.request_id}, headers)

    def _body(self):
        if "application/json" not in self.headers.get("Content-Type", ""):
            self._error(415, "unsupported_media_type", "Send the body as application/json.")
            return None
        try:
            data = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        except json.JSONDecodeError:
            self._error(400, "invalid_json", "The request body is not valid JSON.")
            return None
        if not isinstance(data, dict):
            self._error(400, "invalid_json", "The request body must be a JSON object.")
            return None
        return data

    def _user(self):
        header = self.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            self._error(401, "not_authenticated", "Missing or invalid credentials.", headers={"WWW-Authenticate": "Bearer"})
            return None
        try:
            return read_token(header[7:], "access")["sub"]
        except TokenError as error:
            self._error(401, error.code, "Your access token is not valid.", headers={"WWW-Authenticate": "Bearer"})
            return None

    # ---------------------------------------------------------------- routing
    def _route(self, method):
        self.request_id = self.headers.get("X-Request-ID") or "req_" + uuid.uuid4().hex[:12]
        url = urlparse(self.path)
        path, query = url.path.rstrip("/"), parse_qs(url.query)
        public = {
            ("POST", f"{PREFIX}/auth/login"): self.login,
            ("POST", f"{PREFIX}/auth/refresh"): self.refresh,
            ("POST", f"{PREFIX}/auth/logout"): self.logout,
            ("POST", f"{PREFIX}/auth/register"): self.register,
            ("GET", f"{PREFIX}/health"): lambda q: self._send(200, {"status": "ok"}),
            ("GET", f"{PREFIX}/_debug/stats"): lambda q: self._send(200, STATS),
            ("POST", f"{PREFIX}/_debug/reset"): self.reset,
            ("GET", f"{PREFIX}/_debug/slow"): self.slow,
        }
        handler = public.get((method, path))
        if handler:
            return handler(query)
        if not path.startswith(PREFIX):
            return self._error(404, "not_found", "Unknown path.")

        user_id = self._user()
        if user_id is None:
            return
        self.user_id = user_id
        routes = [
            ("GET", rf"^{PREFIX}/me$", self.me),
            ("GET", rf"^{PREFIX}/conversations$", self.list_conversations),
            ("POST", rf"^{PREFIX}/conversations$", self.create_conversation),
            ("GET", rf"^{PREFIX}/conversations/(?P<cid>[a-z0-9_]+)$", self.get_conversation),
            ("POST", rf"^{PREFIX}/ws-ticket$", self.ws_ticket),
            ("GET", rf"^{PREFIX}/_debug/headers$", self.echo_headers),
            ("GET", rf"^{PREFIX}/_debug/boom$", self.boom),
            ("GET", rf"^{PREFIX}/_debug/stream$", self.stream),
        ]
        allowed = []
        for route_method, pattern, func in routes:
            match = re.match(pattern, path)
            if match:
                if route_method == method:
                    return func(query, **match.groupdict())
                allowed.append(route_method)
        if allowed:
            return self._error(405, "method_not_allowed", f"{method} is not allowed here.", headers={"Allow": ", ".join(allowed)})
        self._error(404, "not_found", "Unknown path.")

    def do_GET(self): self._route("GET")
    def do_POST(self): self._route("POST")
    def do_PUT(self): self._route("PUT")
    def do_PATCH(self): self._route("PATCH")
    def do_DELETE(self): self._route("DELETE")
    def log_message(self, format, *args): pass

    # ---------------------------------------------------------------- auth
    def login(self, query):
        data = self._body()
        if data is None:
            return
        email, password = data.get("email"), data.get("password")
        problems = {}
        if not isinstance(email, str) or not email.strip():
            problems["email"] = ["This field is required."]
        if not isinstance(password, str) or not password:
            problems["password"] = ["This field is required."]
        if problems:
            return self._error(400, "validation_error", "The request data is invalid.", problems)
        user = USERS.get(email.strip().lower())
        with LOCK:
            STATS["login_calls"] += 1
        if not user or not hmac.compare_digest(user["password"], password):
            return self._error(401, "authentication_failed", "Incorrect email or password.")
        with LOCK:
            pair = issue_pair(user["id"])
        self._send(200, {**pair, "user": {"id": user["id"], "email": email.strip().lower(), "name": user["name"]}})

    def refresh(self, query):
        data = self._body()
        if data is None:
            return
        with LOCK:
            STATS["refresh_calls"] += 1
            try:
                payload = read_token(str(data.get("refresh", "")), "refresh")
            except TokenError as error:
                return self._error(401, error.code, "Your session has expired. Please log in again.")
            entry = REFRESH_TOKENS.get(payload["jti"])
            if entry is None or entry["family"] in REVOKED_FAMILIES:
                return self._error(401, "token_invalid", "Your session is no longer valid.")
            if entry["used"]:                                  # reuse of a rotated token: assume theft, revoke the family
                REVOKED_FAMILIES.add(entry["family"])
                return self._error(401, "token_reused", "This session was revoked for your safety.")
            entry["used"] = True
            pair = issue_pair(entry["user"], entry["family"])
        self._send(200, pair)

    def logout(self, query):
        data = self._body()
        if data is not None:
            try:
                payload = read_token(str(data.get("refresh", "")), "refresh")
                REVOKED_FAMILIES.add(payload["fam"])
            except TokenError:
                pass
        self._send(204)

    def register(self, query):
        data = self._body()
        if data is None:
            return
        email, password, name = data.get("email"), data.get("password"), data.get("name")
        problems = {}
        if not isinstance(email, str) or "@" not in email:
            problems["email"] = ["Enter a valid email address."]
        elif email.strip().lower() in USERS:
            problems["email"] = ["A user with this email already exists."]
        if not isinstance(password, str) or len(password) < 8:
            problems["password"] = ["This password is too short. It must contain at least 8 characters."]
        if not isinstance(name, str) or not name.strip():
            problems["name"] = ["This field is required."]
        if problems:
            return self._error(400, "validation_error", "The request data is invalid.", problems)
        USERS[email.strip().lower()] = {"id": "usr_" + uuid.uuid4().hex[:6], "name": name.strip(), "password": password}
        self._send(201, {"detail": "Account created. Check your email to verify your address."})

    def reset(self, query):
        with LOCK:
            STATS.update(login_calls=0, refresh_calls=0)
            REFRESH_TOKENS.clear()
            REVOKED_FAMILIES.clear()
            IDEMPOTENT.clear()
            seed()
            for key in [k for k in USERS if k not in ("ada@example.com", "bo@example.com")]:
                del USERS[key]
        self._send(200, {"reset": True})

    # ---------------------------------------------------------------- API
    def me(self, query):
        user = next(u for u in USERS.items() if u[1]["id"] == self.user_id)
        self._send(200, {"id": self.user_id, "email": user[0], "name": user[1]["name"]})

    def list_conversations(self, query):
        raw = query.get("limit", ["20"])[0]
        if not raw.isdigit() or not 1 <= int(raw) <= MAX_LIMIT:
            return self._error(400, "validation_error", "Invalid query parameters.", {"limit": [f"Must be an integer between 1 and {MAX_LIMIT}."]})
        limit, items = int(raw), CONVERSATIONS.get(self.user_id, [])
        if "cursor" in query:
            try:
                after = json.loads(base64.urlsafe_b64decode(query["cursor"][0]))["after"]
            except Exception:
                return self._error(400, "validation_error", "Invalid query parameters.", {"cursor": ["Invalid cursor."]})
            ids = [c["id"] for c in items]
            items = items[ids.index(after) + 1:] if after in ids else []
        page = items[:limit]
        self._send(200, {"results": page, "next": encode_cursor(page[-1]["id"]) if len(items) > limit else None})

    def get_conversation(self, query, cid):
        for conversation in CONVERSATIONS.get(self.user_id, []):
            if conversation["id"] == cid:
                return self._send(200, conversation)
        self._error(404, "not_found", "Conversation not found.")

    def create_conversation(self, query):
        key = self.headers.get("Idempotency-Key")
        with LOCK:
            if key and (self.user_id, key) in IDEMPOTENT:
                status, payload = IDEMPOTENT[(self.user_id, key)]
                return self._send(status, payload, {"Idempotent-Replayed": "true"})
        data = self._body()
        if data is None:
            return
        title = data.get("title")
        if not isinstance(title, str) or not 1 <= len(title.strip()) <= 200:
            return self._error(400, "validation_error", "The request data is invalid.", {"title": ["This field is required and must be 1 to 200 characters."]})
        with LOCK:
            items = CONVERSATIONS.setdefault(self.user_id, [])
            conversation = {"id": f"cnv_{uuid.uuid4().hex[:6]}", "title": title.strip(), "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
            items.insert(0, conversation)
            if key:
                IDEMPOTENT[(self.user_id, key)] = (201, conversation)
        self._send(201, conversation, {"Location": f"{PREFIX}/conversations/{conversation['id']}"})

    def ws_ticket(self, query):
        self._send(200, {"ticket": "tkt_" + uuid.uuid4().hex, "expires_in": 30})

    # ---------------------------------------------------------------- test helpers
    def echo_headers(self, query):
        self._send(200, {k.lower(): v for k, v in self.headers.items()})

    def boom(self, query):
        self._error(500, "internal_error", "Something went wrong on our side.")

    def slow(self, query):
        time.sleep(int(query.get("ms", ["100"])[0]) / 1000)
        self.request_id = "req_slow"
        self._send(200, {"ok": True})

    def stream(self, query):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Request-ID", self.request_id)
        self.end_headers()
        for i in range(3):
            self.wfile.write(f"event: tick\ndata: {json.dumps({'n': i})}\n\n".encode())
            self.wfile.flush()
            time.sleep(0.25)

if __name__ == "__main__":
    seed()
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Mock backend on http://localhost:{PORT}{PREFIX}  (login: ada@example.com / correct-horse-battery, access token lifetime {ACCESS_TTL}s)", flush=True)
    server.serve_forever()
```


## Server State with TanStack Query › Devtools

Add `<ReactQueryDevtools initialIsOpen={false} />` inside the provider in development: it shows every cache entry, its state and age, and lets you force refetches. It is the quickest way to understand what the cache is doing.


## Forms with React Hook Form and Zod › Validation helpers (pure, tested)

**lib/forms/validators.ts**

```
/** Pure validation helpers, shared by the Zod schemas and by unit tests. The server (Django validators) stays authoritative. */
export function isValidEmail(value: string): boolean {
  const email = value.trim();
  return email.length <= 254 && /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(email);
}

const COMMON_PASSWORDS = new Set(["password", "12345678", "123456789", "qwertyui", "iloveyou", "11111111", "password1"]);

/** Return a list of human-readable problems; an empty list means the password looks acceptable. */
export function passwordProblems(password: string, email = ""): string[] {
  const problems: string[] = [];
  if (password.length < 8) problems.push("Use at least 8 characters.");
  if (password.length > 128) problems.push("Use 128 characters or fewer.");
  if (password.length > 0 && /^\d+$/.test(password)) problems.push("Don\u2019t use only numbers.");
  if (COMMON_PASSWORDS.has(password.toLowerCase())) problems.push("That password is too common.");
  const local = email.split("@")[0]?.toLowerCase() ?? "";
  if (local.length >= 4 && password.toLowerCase().includes(local)) problems.push("Don\u2019t include your email name in the password.");
  return problems;
}
```

Email and password checks are plain functions, so unit tests can hammer them with edge cases and the schemas simply call them. The server (Django’s validators, Chapter 13) is always **authoritative**: client validation exists for fast, friendly feedback, never for security.


## The Pages

With the pieces above, the pages are short. The list component handles every state the design in Chapter 9 requires: loading, error with retry, empty, content, and "load more":

**components/chat/ConversationList.tsx**

```
"use client";

import { messageForError } from "@/lib/api/errors";
import { flattenPages } from "@/lib/query/cache-updates";
import { useConversations } from "@/lib/query/hooks";

export function ConversationList() {
  const query = useConversations(20);

  if (query.isPending) return <p aria-busy="true">Loading your conversations...</p>;

  if (query.isError) {
    return (
      <div role="alert">
        <p>{messageForError(query.error)}</p>
        <button onClick={() => query.refetch()}>Try again</button>
      </div>
    );
  }

  const conversations = flattenPages(query.data);
  if (conversations.length === 0) {
    return <p>No conversations yet. Create one above, for example: &ldquo;Draft a polite reply to a customer&rdquo;.</p>;
  }

  return (
    <>
      <ul>
        {conversations.map((conversation) => (
          <li key={conversation.id}>
            {conversation.title}{" "}
            <time dateTime={conversation.created_at}>{new Date(conversation.created_at).toLocaleDateString()}</time>
          </li>
        ))}
      </ul>
      {query.hasNextPage ? (
        <button onClick={() => query.fetchNextPage()} disabled={query.isFetchingNextPage} aria-busy={query.isFetchingNextPage}>
          {query.isFetchingNextPage ? "Loading..." : "Load more"}
        </button>
      ) : null}
    </>
  );
}
```

**components/LogoutButton.tsx**

```
"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { logoutRequest } from "@/lib/api/auth";
import { resetUiStore } from "@/lib/state/ui-store";

export function LogoutButton() {
  const queryClient = useQueryClient();
  const [pending, setPending] = useState(false);

  async function onClick() {
    setPending(true);
    await logoutRequest();                 // clears the HttpOnly cookies and revokes the session
    queryClient.clear();                   // forget every cached answer that belonged to this user
    resetUiStore();                        // and their unsent drafts
    window.location.assign("/login");      // a full page load guarantees no stale in-memory state survives
  }

  return <button onClick={onClick} disabled={pending}>{pending ? "Logging out..." : "Log out"}</button>;
}
```

**app/login/page.tsx**

```
import { Suspense } from "react";
import { LoginForm } from "@/components/forms/LoginForm";

export default function LoginPage() {
  // useSearchParams() inside LoginForm requires a Suspense boundary
  return (
    <main>
      <Suspense fallback={<p>Loading...</p>}>
        <LoginForm />
      </Suspense>
      <p>No account? <a href="/signup">Create one</a></p>
    </main>
  );
}
```

**app/signup/page.tsx**

```
import { SignupForm } from "@/components/forms/SignupForm";

export default function SignupPage() {
  return (
    <main>
      <SignupForm />
      <p>Already registered? <a href="/login">Log in</a></p>
    </main>
  );
}
```

**app/chat/page.tsx**

```
"use client";

import { ConversationList } from "@/components/chat/ConversationList";
import { NewConversationForm } from "@/components/forms/NewConversationForm";
import { LogoutButton } from "@/components/LogoutButton";
import { useMe } from "@/lib/query/hooks";
import { useUiStore } from "@/lib/state/ui-store";

export default function ChatPage() {
  const me = useMe();
  const sidebarOpen = useUiStore((state) => state.sidebarOpen);          // a selector: re-render only when THIS value changes
  const toggleSidebar = useUiStore((state) => state.toggleSidebar);

  return (
    <main>
      <header>
        <h1>Chat</h1>
        <span>{me.data ? `Signed in as ${me.data.email}` : null}</span>
        <button onClick={toggleSidebar} aria-expanded={sidebarOpen}>{sidebarOpen ? "Hide" : "Show"} conversations</button>
        <LogoutButton />
      </header>
      {sidebarOpen ? (
        <aside>
          <NewConversationForm />
          <ConversationList />
        </aside>
      ) : null}
    </main>
  );
}
```

Everything the chat page needs is one line per concern: `useMe()` for the user, `useUiStore(selector)` for the sidebar, `NewConversationForm` and `ConversationList` for the data. There is no `useEffect` fetching code and no hand-managed loading flags anywhere.


## Testing the Frontend: Levels and Tools

| **Level** | **Covers** | **Tools** |
|---|---|---|
| **Pure unit tests** (done) | Validators, schemas, error mapping, redirects, cache updates, drafts | Node’s built-in test runner via `tsx` (25 tests) |
| **Client tests with a fake fetch** (done) | URLs, headers, errors, timeouts, cancellation | Same runner (10 tests) |
| **Integration tests against a real HTTP backend** (done) | The gateway and auth handlers end to end | Same runner + the mock backend (30 tests) |
| **Component markup tests** (done, small) | Accessible field wiring | `react-dom/server` rendering (4 tests) |
| **Component tests with user events** (Chapter 39) | Typing, submitting, loading and error states in the real DOM | Vitest or Jest, Testing Library, MSW (mocks network) |
| **End-to-end tests** (Chapter 39) | Sign up, log in, create a conversation, with a real browser | Playwright |

Add this script to `package.json` and run everything with one command (it needs Python 3 for the mock backend):

**package.json (add)**

```
{
  "scripts": {
    "test": "tsx --test tests/*.test.ts tests/*.test.tsx"
  }
}
```

**tests/unit.test.ts**

```
import assert from "node:assert/strict";
import { test, describe } from "node:test";
import { ApiError, errorFromResponse, isRetryable, messageForError } from "../lib/api/errors";
import { buildQuery } from "../lib/api/query-string";
import { decodeJwtPayload, isExpiringSoon, tokenExpiresAt } from "../lib/auth/jwt";
import { decideRedirect, safeNextPath } from "../lib/auth/redirects";
import { clearCookie, parseCookies, serializeCookie } from "../lib/bff/cookies";
import { conversationSchema, loginSchema, signupSchema } from "../lib/forms/schemas";
import { mapApiErrorToForm } from "../lib/forms/server-errors";
import { isValidEmail, passwordProblems } from "../lib/forms/validators";
import { flattenPages, prependToFirstPage, removeItem, replaceItem, uniqueById } from "../lib/query/cache-updates";
import { retryDelay, shouldRetry } from "../lib/query/retry";
import { clearDraft, getDraft, setDraft } from "../lib/state/drafts";

function fakeJwt(payload: object): string {
  const encode = (value: object) => Buffer.from(JSON.stringify(value)).toString("base64url");
  return `${encode({ alg: "HS256", typ: "JWT" })}.${encode(payload)}.signature`;
}

describe("jwt helpers", () => {
  test("decodes the payload and the expiry without verifying", () => {
    const token = fakeJwt({ sub: "usr_1", exp: 1_800_000_000, name: "Zo\u00eb \u2603" });
    assert.equal(decodeJwtPayload(token)?.sub, "usr_1");
    assert.equal(decodeJwtPayload(token)?.name, "Zo\u00eb \u2603");     // UTF-8 survives
    assert.equal(tokenExpiresAt(token), 1_800_000_000);
  });
  test("garbage is handled, never thrown", () => {
    for (const bad of ["", "abc", "a.b", "a.b.c", "a.!!!.c", `x.${Buffer.from("[1]").toString("base64url")}.z`]) {
      assert.equal(decodeJwtPayload(bad), null, bad);
    }
    assert.equal(tokenExpiresAt(fakeJwt({ sub: "x" })), null);
  });
  test("isExpiringSoon respects the skew", () => {
    const token = fakeJwt({ exp: 1000 });
    assert.equal(isExpiringSoon(token, 900, 30), false);   // 100 s left
    assert.equal(isExpiringSoon(token, 975, 30), true);    // 25 s left
    assert.equal(isExpiringSoon(token, 1000, 0), true);    // expired
    assert.equal(isExpiringSoon(undefined, 0), true);
    assert.equal(isExpiringSoon("not-a-token", 0), true);
  });
});

describe("cookies", () => {
  test("parseCookies handles spaces, encoding, duplicates and junk", () => {
    assert.deepEqual(parseCookies("a=1; b=hello%20world;  c=x=y; novalue; =oops; a=2"), { a: "1", b: "hello world", c: "x=y" });
    assert.deepEqual(parseCookies(null), {});
    assert.deepEqual(parseCookies("bad=%E0%A4%A"), { bad: "%E0%A4%A" });
  });
  test("session cookies are HttpOnly, SameSite=Lax, and Secure only when asked", () => {
    const plain = serializeCookie("ai_access", "tok/en+1", { maxAgeSeconds: 900.7, secure: false });
    assert.match(plain, /^ai_access=tok%2Fen%2B1; Path=\/; Max-Age=900; HttpOnly; SameSite=Lax$/);
    assert.ok(serializeCookie("a", "b", { maxAgeSeconds: 1, secure: true }).endsWith("; Secure"));
    assert.match(clearCookie("ai_access", true), /Max-Age=0/);
    assert.match(serializeCookie("a", "b", { maxAgeSeconds: -50, secure: false }), /Max-Age=0/);
  });
});

describe("api errors", () => {
  test("parses the standard error format", async () => {
    const response = new Response(JSON.stringify({ error: { code: "validation_error", message: "Bad.", details: { title: ["Required."], odd: "text" } }, request_id: "req_1" }),
      { status: 400, headers: { "retry-after": "7" } });
    const error = await errorFromResponse(response);
    assert.deepEqual([error.status, error.code, error.requestId, error.retryAfter], [400, "validation_error", "req_1", 7]);
    assert.deepEqual(error.details, { title: ["Required."], odd: ["text"] });
  });
  test("survives HTML, empty and weird bodies", async () => {
    const html = await errorFromResponse(new Response("<h1>Bad gateway</h1>", { status: 502, headers: { "x-request-id": "req_h" } }));
    assert.deepEqual([html.code, html.requestId], ["internal_error", "req_h"]);
    assert.equal((await errorFromResponse(new Response(null, { status: 404 }))).code, "not_found");
    assert.equal((await errorFromResponse(new Response("[]", { status: 401 }))).code, "not_authenticated");
    assert.equal((await errorFromResponse(new Response(JSON.stringify({ error: "nope" }), { status: 429 }))).code, "rate_limited");
  });
  test("friendly messages and retry rules", () => {
    assert.match(messageForError(new ApiError({ status: 0, code: "network_error", message: "x" })), /couldn\u2019t reach/);
    assert.match(messageForError(new ApiError({ status: 500, code: "weird", message: "stack trace here" })), /Something went wrong/);
    assert.equal(messageForError(new ApiError({ status: 400, code: "weird", message: "Custom server text" })), "Custom server text");
    assert.equal(isRetryable(new ApiError({ status: 0, code: "network_error", message: "" })), true);
    assert.equal(isRetryable(new ApiError({ status: 503, code: "upstream_unavailable", message: "" })), true);
    assert.equal(isRetryable(new ApiError({ status: 404, code: "not_found", message: "" })), false);
    assert.equal(isRetryable(new ApiError({ status: 401, code: "not_authenticated", message: "" })), false);
    assert.equal(isRetryable(new Error("boom")), false);
  });
  test("TanStack retry helpers", () => {
    const network = new ApiError({ status: 0, code: "network_error", message: "" });
    assert.deepEqual([0, 1, 2, 3].map((n) => shouldRetry(n, network)), [true, true, false, false]);
    assert.equal(shouldRetry(0, new ApiError({ status: 400, code: "validation_error", message: "" })), false);
    assert.deepEqual([0, 1, 2, 5, 9].map(retryDelay), [500, 1000, 2000, 8000, 8000]);
  });
});

describe("query strings", () => {
  test("skips empty values and joins arrays", () => {
    assert.equal(buildQuery({ limit: 20, cursor: null, q: "", status: ["ready", "processing"], empty: [], flag: false }), "?limit=20&status=ready%2Cprocessing&flag=false");
    assert.equal(buildQuery({}), "");
    assert.equal(buildQuery({ q: "a b&c=d" }), "?q=a+b%26c%3Dd");
  });
});

describe("redirects", () => {
  test("safeNextPath blocks open redirects", () => {
    const attacks = ["//evil.example", "https://evil.example/x", "/\\evil.example", "javascript:alert(1)", "/%2F%2Fevil.example", "/ok/../..//evil", "\n/chat", "chat", "/a\u0000b", "http:evil.example", "/" + "x".repeat(400)];
    for (const attack of attacks) {
      const result = safeNextPath(attack);
      assert.ok(result === "/chat" || (result.startsWith("/") && !result.startsWith("//") && !result.includes("://")), `${attack} -> ${result}`);
    }
    assert.equal(safeNextPath("//evil.example"), "/chat");
    assert.equal(safeNextPath("https://evil.example"), "/chat");
    assert.equal(safeNextPath("/%2F%2Fevil.example"), "/chat");
  });
  test("safeNextPath keeps legitimate paths", () => {
    assert.equal(safeNextPath("/chat/abc?x=1#top"), "/chat/abc?x=1#top");
    assert.equal(safeNextPath("/settings"), "/settings");
    assert.equal(safeNextPath(null), "/chat");
    assert.equal(safeNextPath(undefined, "/home"), "/home");
  });
  test("decideRedirect protects pages and bounces logged-in users off the login page", () => {
    assert.equal(decideRedirect("/chat", "", false), "/login?next=%2Fchat");
    assert.equal(decideRedirect("/chat/42", "?tab=a", false), "/login?next=%2Fchat%2F42%3Ftab%3Da");
    assert.equal(decideRedirect("/chat", "", true), null);
    assert.equal(decideRedirect("/login", "", true), "/chat");
    assert.equal(decideRedirect("/login", "", false), null);
    assert.equal(decideRedirect("/", "", false), null);
    assert.equal(decideRedirect("/pricing", "", false), null);
    assert.equal(decideRedirect("/chatty", "", false), null);          // a prefix match must respect path boundaries
    assert.equal(decideRedirect("/billing/invoices", "", false), "/login?next=%2Fbilling%2Finvoices");
  });
});

describe("validators and schemas", () => {
  test("emails", () => {
    for (const ok of ["ada@example.com", " bo+tag@sub.example.org "]) assert.equal(isValidEmail(ok), true, ok);
    for (const bad of ["", "ada", "ada@", "@example.com", "ada@example", "a b@example.com", "a@b.c", "x".repeat(250) + "@example.com"]) assert.equal(isValidEmail(bad), false, bad);
  });
  test("password problems", () => {
    assert.deepEqual(passwordProblems("correct-horse-battery", "ada@example.com"), []);
    assert.deepEqual(passwordProblems("short"), ["Use at least 8 characters."]);
    assert.ok(passwordProblems("12345678").length >= 2);
    assert.deepEqual(passwordProblems("Password"), ["That password is too common."]);
    assert.deepEqual(passwordProblems("ada-lovelace-1", "ada.lovelace@example.com").length, 0);
    assert.deepEqual(passwordProblems("xxada.lovelacexx", "ada.lovelace@example.com"), ["Don\u2019t include your email name in the password."]);
  });
  test("login schema trims the email and explains each problem", () => {
    const ok = loginSchema.safeParse({ email: "  ada@example.com ", password: "x" });
    assert.ok(ok.success && ok.data.email === "ada@example.com");
    const bad = loginSchema.safeParse({ email: "nope", password: "" });
    assert.ok(!bad.success);
    const messages = Object.fromEntries(bad.error.issues.map((i) => [i.path.join("."), i.message]));
    assert.deepEqual(messages, { email: "Enter an email like name@example.com.", password: "Enter your password." });
  });
  test("signup schema checks the password rules and the confirmation", () => {
    const good = { name: " Ada ", email: "ada@example.com", password: "correct-horse-battery", confirmPassword: "correct-horse-battery" };
    const parsed = signupSchema.safeParse(good);
    assert.ok(parsed.success && parsed.data.name === "Ada");
    const bad = signupSchema.safeParse({ ...good, password: "short", confirmPassword: "different" });
    assert.ok(!bad.success);
    const byField = bad.error.issues.map((i) => `${i.path.join(".")}: ${i.message}`);
    assert.deepEqual(byField, ["password: Use at least 8 characters.", "confirmPassword: Passwords do not match."]);
    assert.ok(!signupSchema.safeParse({ ...good, name: "" }).success);
  });
  test("conversation schema", () => {
    assert.ok(conversationSchema.safeParse({ title: "  Trip plan " }).success);
    assert.ok(!conversationSchema.safeParse({ title: "   " }).success);
    assert.ok(!conversationSchema.safeParse({ title: "x".repeat(201) }).success);
  });
});

describe("server errors mapped to forms", () => {
  const fields = ["email", "password", "name"] as const;
  test("field errors stay with their fields, the rest go to the form", () => {
    const error = new ApiError({ status: 400, code: "validation_error", message: "Bad", details: { email: ["Taken."], non_field_errors: ["Try later."], unknown: ["Odd."] } });
    assert.deepEqual(mapApiErrorToForm(error, fields), { fieldErrors: [{ field: "email", message: "Taken." }], formError: "Try later. Odd." });
  });
  test("only field errors means no form-level message", () => {
    const error = new ApiError({ status: 400, code: "validation_error", message: "Bad", details: { password: ["Too short.", "Too common."] } });
    assert.deepEqual(mapApiErrorToForm(error, fields), { fieldErrors: [{ field: "password", message: "Too short. Too common." }], formError: null });
  });
  test("other errors become friendly form messages", () => {
    assert.equal(mapApiErrorToForm(new ApiError({ status: 401, code: "authentication_failed", message: "x" }), fields).formError, "Incorrect email or password.");
    assert.match(mapApiErrorToForm(new ApiError({ status: 0, code: "network_error", message: "x" }), fields).formError!, /couldn\u2019t reach/);
    assert.match(mapApiErrorToForm(new Error("weird"), fields).formError!, /Something went wrong/);
    assert.match(mapApiErrorToForm(new ApiError({ status: 400, code: "validation_error", message: "Bad", details: {} }), fields).formError!, /Bad/);
  });
});

describe("optimistic cache updates", () => {
  const page = (ids: string[], next: string | null) => ({ results: ids.map((id) => ({ id, title: id })), next });
  const data = { pages: [page(["a", "b"], "c1"), page(["c"], null)], pageParams: [null, "c1"] };
  test("prepend puts the item first and never mutates", () => {
    const frozen = structuredClone(data);
    const next = prependToFirstPage(data, { id: "new", title: "New" });
    assert.deepEqual(flattenPages(next).map((x) => x.id), ["new", "a", "b", "c"]);
    assert.deepEqual(data, frozen);
    assert.deepEqual(flattenPages(prependToFirstPage(undefined, { id: "n", title: "N" })).map((x) => x.id), ["n"]);
    assert.deepEqual(flattenPages(prependToFirstPage(data, { id: "a", title: "A again" })).map((x) => x.title), ["A again", "b", "c"]);
  });
  test("replace, remove and unique", () => {
    assert.deepEqual(flattenPages(replaceItem(data, "b", { id: "b2", title: "B2" })).map((x) => x.id), ["a", "b2", "c"]);
    assert.deepEqual(flattenPages(removeItem(data, "a")).map((x) => x.id), ["b", "c"]);
    assert.equal(removeItem(undefined, "a"), undefined);
    assert.deepEqual(uniqueById([{ id: "1" }, { id: "2" }, { id: "1" }]), [{ id: "1" }, { id: "2" }]);
    assert.deepEqual(flattenPages(undefined), []);
  });
});

describe("composer drafts", () => {
  test("saving, reading, clearing and trimming", () => {
    let drafts = setDraft({}, "c1", "hello", 1);
    assert.equal(getDraft(drafts, "c1"), "hello");
    drafts = setDraft(drafts, "c1", "   ", 2);                       // blank text removes the draft
    assert.equal(getDraft(drafts, "c1"), "");
    assert.equal(getDraft(clearDraft(setDraft({}, "c9", "x", 1), "c9"), "c9"), "");
    assert.equal(getDraft(setDraft({}, "c1", "x".repeat(9000), 1), "c1").length, 8000);
  });
  test("only the most recent drafts are kept", () => {
    let drafts = {};
    for (let i = 0; i < 25; i++) drafts = setDraft(drafts, `c${i}`, `text ${i}`, i, 20);
    assert.equal(Object.keys(drafts).length, 20);
    assert.equal(getDraft(drafts, "c24"), "text 24");
    assert.equal(getDraft(drafts, "c0"), "");
  });
});
```
