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
