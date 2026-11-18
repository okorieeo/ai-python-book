import { ApiClient } from "../src/apiClient";
import { ApiError, NetworkError, SessionExpiredError, TimeoutError } from "../src/errors";
import { MemoryStore } from "../src/storage";
import { TokenStore } from "../src/tokenStore";
import { FakeFetch, Scripted, rejection } from "./helpers";

const BASE = "https://api.example.com";

async function setup(script: Array<Scripted | ((c: any) => Scripted)>, opts: Partial<ConstructorParameters<typeof ApiClient>[0]> = {}, signedIn = true) {
  const fake = new FakeFetch(script);
  const tokenStore = new TokenStore(new MemoryStore());
  if (signedIn) await tokenStore.set({ access: "old-access", refresh: "old-refresh" });
  const delays: number[] = [];
  let n = 0;
  const onSessionExpired = jest.fn();
  const client = new ApiClient({
    baseUrl: BASE, tokenStore, fetch: fake.fetch, onSessionExpired,
    sleep: async (ms) => { delays.push(ms); },
    random: () => 0.5, makeRequestId: () => `req-${++n}`, ...opts,
  });
  return { fake, tokenStore, client, delays, onSessionExpired };
}

describe("requests", () => {
  test("a GET carries the token, a request id and asks for JSON", async () => {
    const { fake, client } = await setup([{ body: { hello: "world" } }]);
    expect(await client.get("/api/v1/me/")).toEqual({ hello: "world" });
    expect(fake.calls[0]).toMatchObject({ url: `${BASE}/api/v1/me/`, method: "GET" });
    expect(fake.calls[0]!.headers).toMatchObject({ Authorization: "Bearer old-access", Accept: "application/json", "X-Request-ID": "req-1" });
    expect(fake.calls[0]!.headers["Content-Type"]).toBeUndefined();
  });

  test("public endpoints send no token", async () => {
    const { fake, client } = await setup([{ body: {} }]);
    await client.post("/api/v1/auth/login/", { email: "a@b.c" }, { auth: false });
    expect(fake.calls[0]!.headers.Authorization).toBeUndefined();
  });

  test("a POST sends its body as JSON, and 204 gives undefined", async () => {
    const { fake, client } = await setup([{ status: 204 }]);
    expect(await client.post("/x/", { a: 1 })).toBeUndefined();
    expect(fake.calls[0]!.body).toBe('{"a":1}');
    expect(fake.calls[0]!.headers["Content-Type"]).toBe("application/json");
  });

  test("an unreadable success body is an error, not a crash", async () => {
    const { client } = await setup([{ text: "<html>oops</html>" }]);
    await expect(client.get("/x/")).rejects.toMatchObject({ code: "invalid_json" });
  });
});

describe("errors are normalised", () => {
  test("Django REST Framework errors keep their code, message and details", async () => {
    const { client } = await setup([{ status: 403, body: { detail: "You have reached your plan's limit.", code: "limit_reached", limit: 30, used: 30 } }]);
    const error = await rejection(client.get("/x/"));
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 403, code: "limit_reached", message: "You have reached your plan's limit." });
    expect(error.details).toMatchObject({ limit: 30, used: 30 }); // numbers stay numbers (Chapter 35)
  });
  test("an HTML error page never becomes a message", async () => {
    const { client } = await setup([{ status: 500, text: "<html><body>Traceback (most recent call last)</body></html>" }], { maxRetries: 0 });
    const error = await rejection(client.get("/x/"));
    expect(error.message).toBe("Request failed (500)");
    expect(error.code).toBe("http_500");
  });
  test("Retry-After is read in seconds", async () => {
    const { client } = await setup([{ status: 429, headers: { "Retry-After": "7" }, body: {} }], { maxRetries: 0 });
    const error = await rejection(client.get("/x/"));
    expect(error.retryAfterMs).toBe(7000);
  });
});

describe("retries", () => {
  test("a GET is retried on 503 with growing, randomised delays", async () => {
    const { client, fake, delays } = await setup([{ status: 503 }, { status: 502 }, { body: { ok: true } }]);
    expect(await client.get("/x/")).toEqual({ ok: true });
    expect(fake.calls).toHaveLength(3);
    expect(delays).toEqual([375, 750]); // base 500 and 1000, "equal jitter" with random = 0.5
  });
  test("the server's Retry-After wins over our own delay", async () => {
    const { client, delays } = await setup([{ status: 429, headers: { "Retry-After": "2" } }, { body: {} }]);
    await client.get("/x/");
    expect(delays).toEqual([2000]);
  });
  test("gives up after maxRetries", async () => {
    const { client, fake } = await setup([{ status: 503 }, { status: 503 }, { status: 503 }], { maxRetries: 2 });
    await expect(client.get("/x/")).rejects.toMatchObject({ status: 503 });
    expect(fake.calls).toHaveLength(3);
  });
  test("a POST without an idempotency key is never repeated", async () => {
    const { client, fake } = await setup([{ throws: new Error("socket hang up") }, { body: {} }]);
    await expect(client.post("/orders/", { item: 1 })).rejects.toBeInstanceOf(NetworkError);
    expect(fake.calls).toHaveLength(1); // the order may already have been created: do not risk a second one
  });
  test("a POST WITH a key is retried, and every attempt carries the same key", async () => {
    const { client, fake } = await setup([{ throws: new Error("reset") }, { status: 503 }, { body: { id: 9 } }]);
    expect(await client.post("/orders/", { item: 1 }, { idempotencyKey: "order-abc" })).toEqual({ id: 9 });
    expect(fake.calls.map((c) => c.headers["Idempotency-Key"])).toEqual(["order-abc", "order-abc", "order-abc"]);
  });
  test("client errors are not retried", async () => {
    for (const status of [400, 403, 404, 409, 422]) {
      const { client, fake } = await setup([{ status, body: { detail: "no" } }]);
      await expect(client.get("/x/")).rejects.toMatchObject({ status });
      expect(fake.calls).toHaveLength(1);
    }
  });
});

describe("token refresh", () => {
  const refreshed = { body: { access: "new-access", refresh: "new-refresh", expires_in: 300 } };

  test("a 401 refreshes the token and repeats the request once", async () => {
    const { client, fake, tokenStore } = await setup([{ status: 401 }, refreshed, { body: { ok: 1 } }]);
    expect(await client.get("/me/")).toEqual({ ok: 1 });
    expect(fake.calls.map((c) => c.url)).toEqual([`${BASE}/me/`, `${BASE}/api/v1/auth/refresh/`, `${BASE}/me/`]);
    expect(JSON.parse(fake.calls[1]!.body!)).toEqual({ refresh: "old-refresh" });
    expect(fake.calls[1]!.headers.Authorization).toBeUndefined();
    expect(fake.calls[2]!.headers.Authorization).toBe("Bearer new-access");
    expect((await tokenStore.get())?.refresh).toBe("new-refresh"); // rotated refresh tokens are kept
  });

  test("the old refresh token is kept if the server does not rotate it", async () => {
    const { client, tokenStore } = await setup([{ status: 401 }, { body: { access: "a2" } }, { body: {} }]);
    await client.get("/me/");
    expect(await tokenStore.get()).toMatchObject({ access: "a2", refresh: "old-refresh" });
  });

  test("many requests failing at once share ONE refresh", async () => {
    let refreshCalls = 0;
    const respond = (c: { url: string; headers: Record<string, string> }): Scripted => {
      if (c.url.endsWith("/api/v1/auth/refresh/")) { refreshCalls++; return refreshed; }
      return c.headers.Authorization === "Bearer new-access" ? { body: { ok: true } } : { status: 401 };
    };
    const { client } = await setup(Array.from({ length: 12 }, () => respond));
    const results = await Promise.all([client.get("/a/"), client.get("/b/"), client.get("/c/")]);
    expect(results).toEqual([{ ok: true }, { ok: true }, { ok: true }]);
    expect(refreshCalls).toBe(1);
  });

  test("a second 401 after refreshing is an error, not a loop", async () => {
    const { client, fake } = await setup([{ status: 401 }, refreshed, { status: 401, body: { detail: "Nope" } }]);
    await expect(client.get("/me/")).rejects.toMatchObject({ status: 401 });
    expect(fake.calls).toHaveLength(3);
  });

  test("a refused refresh token signs the user out, once", async () => {
    const { client, tokenStore, onSessionExpired } = await setup([{ status: 401 }, { status: 401, body: { detail: "Token is invalid" } }]);
    await expect(client.get("/me/")).rejects.toBeInstanceOf(SessionExpiredError);
    expect(await tokenStore.get()).toBeNull();
    expect(onSessionExpired).toHaveBeenCalledTimes(1);
  });

  test("being offline during a refresh does NOT sign the user out", async () => {
    const { client, tokenStore, onSessionExpired } = await setup([{ status: 401 }, { throws: new Error("offline") }], { maxRetries: 0 });
    await expect(client.get("/me/")).rejects.toBeInstanceOf(NetworkError);
    expect(await tokenStore.get()).toMatchObject({ refresh: "old-refresh" });
    expect(onSessionExpired).not.toHaveBeenCalled();
  });

  test("a server error during refresh keeps the tokens", async () => {
    const { client, tokenStore } = await setup([{ status: 401 }, { status: 503 }], { maxRetries: 0 });
    await expect(client.get("/me/")).rejects.toMatchObject({ status: 503 });
    expect(await tokenStore.get()).not.toBeNull();
  });

  test("no tokens at all means signed out", async () => {
    const { client } = await setup([{ status: 401 }], {}, false);
    await expect(client.get("/me/")).rejects.toBeInstanceOf(SessionExpiredError);
  });

  test("an access token about to expire is refreshed before the request", async () => {
    const { client, fake, tokenStore } = await setup([refreshed, { body: {} }], { now: () => 1_000_000 });
    await tokenStore.set({ access: "old-access", refresh: "old-refresh", accessExpiresAt: 1_000_000 + 10_000 });
    await client.get("/me/");
    expect(fake.calls[0]!.url).toContain("/auth/refresh/");
    expect(fake.calls[1]!.headers.Authorization).toBe("Bearer new-access");
  });

  test("a token with plenty of time left is used as it is", async () => {
    const { client, fake, tokenStore } = await setup([{ body: {} }], { now: () => 1_000_000 });
    await tokenStore.set({ access: "old-access", refresh: "r", accessExpiresAt: 1_000_000 + 600_000 });
    await client.get("/me/");
    expect(fake.calls).toHaveLength(1);
  });
});

describe("timeouts, cancelling and logging", () => {
  test("a request that never answers times out", async () => {
    jest.useFakeTimers();
    try {
      const { client } = await setup([{ hang: true }], { timeoutMs: 5000, maxRetries: 0 });
      const pending = rejection(client.get("/slow/"));
      await jest.advanceTimersByTimeAsync(5001);
      expect(await pending).toBeInstanceOf(TimeoutError);
    } finally {
      jest.useRealTimers();
    }
  });

  test("cancelling is not reported as a network failure, and is not retried", async () => {
    const { client, fake } = await setup([{ hang: true }]);
    const controller = new AbortController();
    const pending = rejection(client.get("/x/", { signal: controller.signal }));
    controller.abort();
    const error = await pending;
    expect(error).not.toBeInstanceOf(NetworkError);
    expect(error.name).toBe("AbortError");
    expect(fake.calls).toHaveLength(1);
  });

  test("the log never contains tokens, bodies or headers", async () => {
    const events: unknown[] = [];
    const { client } = await setup([{ body: { secret: "response-secret" } }], { onLog: (e) => events.push(e) });
    await client.post("/x/", { password: "hunter2" });
    const text = JSON.stringify(events);
    expect(text).toContain('"status":200');
    for (const leaked of ["old-access", "hunter2", "response-secret", "Bearer"]) expect(text).not.toContain(leaked);
  });
});
