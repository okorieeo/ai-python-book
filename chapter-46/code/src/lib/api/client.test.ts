// @vitest-environment node
import { beforeEach, describe, expect, it } from "vitest";
import { createApi, unwrap } from "./client";
import { ApiError } from "./errors";
import { clearSession, getAccessToken, setAccessToken } from "../auth/session";

const BASE = "http://api.test";
const json = (body: unknown, status = 200, headers: Record<string, string> = {}) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json", ...headers } });

const conversations = { count: 0, next: null, previous: null, results: [] };

beforeEach(() => clearSession());

describe("API client", () => {
  it("sends the access token as a Bearer header", async () => {
    setAccessToken("tok_1");
    const seen: string[] = [];
    const api = createApi(async (request) => {
      seen.push(request.headers.get("Authorization") ?? "");
      return json(conversations);
    }, BASE);

    await unwrap(api.GET("/api/v1/conversations/", { params: { query: {} } }));
    expect(seen).toEqual(["Bearer tok_1"]);
  });

  it("refreshes once on a 401 and retries the original request", async () => {
    setAccessToken("expired");
    const calls: string[] = [];
    const api = createApi(async (request) => {
      const { pathname } = new URL(request.url);
      calls.push(`${request.method} ${pathname} ${request.headers.get("Authorization") ?? "-"}`);
      if (pathname === "/api/v1/auth/refresh/") return json({ access: "fresh" });
      return request.headers.get("Authorization") === "Bearer fresh" ? json(conversations) : json({ error: { code: "not_authenticated", message: "no" } }, 401);
    }, BASE);

    const data = await unwrap(api.GET("/api/v1/conversations/", { params: { query: {} } }));
    expect(data.count).toBe(0);
    expect(calls).toEqual([
      "GET /api/v1/conversations/ Bearer expired",
      "POST /api/v1/auth/refresh/ -",
      "GET /api/v1/conversations/ Bearer fresh",
    ]);
    expect(getAccessToken()).toBe("fresh");
  });

  it("shares ONE refresh between simultaneous 401s", async () => {
    setAccessToken("expired");
    let refreshes = 0;
    const api = createApi(async (request) => {
      const { pathname } = new URL(request.url);
      if (pathname === "/api/v1/auth/refresh/") {
        refreshes += 1;
        await new Promise((resolve) => setTimeout(resolve, 10));
        return json({ access: "fresh" });
      }
      return request.headers.get("Authorization") === "Bearer fresh" ? json(conversations) : json({ error: { code: "x", message: "x" } }, 401);
    }, BASE);

    await Promise.all([
      unwrap(api.GET("/api/v1/conversations/", { params: { query: {} } })),
      unwrap(api.GET("/api/v1/conversations/", { params: { query: {} } })),
      unwrap(api.GET("/api/v1/conversations/", { params: { query: {} } })),
    ]);
    expect(refreshes).toBe(1);
  });

  it("gives up with the 401 when the refresh fails, and clears the token", async () => {
    setAccessToken("expired");
    const api = createApi(async (request) => {
      const { pathname } = new URL(request.url);
      if (pathname === "/api/v1/auth/refresh/") return json({ error: { code: "x", message: "x" } }, 401);
      return json({ error: { code: "not_authenticated", message: "no" } }, 401);
    }, BASE);

    await expect(unwrap(api.GET("/api/v1/conversations/", { params: { query: {} } }))).rejects.toMatchObject({ status: 401 });
    expect(getAccessToken()).toBeNull();
  });

  it("does not try to refresh when the LOGIN call itself returns 401", async () => {
    const paths: string[] = [];
    const api = createApi(async (request) => {
      paths.push(new URL(request.url).pathname);
      return json({ error: { code: "invalid_credentials", message: "nope" } }, 401);
    }, BASE);

    await expect(
      unwrap(api.POST("/api/v1/auth/login/", { body: { email: "a@b.co", password: "x" } })),
    ).rejects.toMatchObject({ status: 401, code: "invalid_credentials" });
    expect(paths).toEqual(["/api/v1/auth/login/"]);
  });

  it("turns a 429 into an ApiError with retryAfter", async () => {
    const api = createApi(async () => json({ error: { code: "throttled", message: "slow down" } }, 429, { "Retry-After": "20" }), BASE);
    const error = await unwrap(api.GET("/api/v1/conversations/", { params: { query: {} } })).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 429, retryAfter: 20 });
  });

  it("reports a dropped connection as status 0", async () => {
    const api = createApi(async () => {
      throw new TypeError("fetch failed");
    }, BASE);
    await expect(api.GET("/api/v1/conversations/", { params: { query: {} } })).rejects.toMatchObject({ status: 0, code: "network_error" });
  });

  it("keeps the request body when it has to retry a POST", async () => {
    setAccessToken("expired");
    const bodies: string[] = [];
    const api = createApi(async (request) => {
      const { pathname } = new URL(request.url);
      if (pathname === "/api/v1/auth/refresh/") return json({ access: "fresh" });
      bodies.push(await request.clone().text());
      return request.headers.get("Authorization") === "Bearer fresh"
        ? json({ public_id: "1", title: "Hi", created_at: "t", updated_at: "t" }, 201)
        : json({ error: { code: "x", message: "x" } }, 401);
    }, BASE);

    await unwrap(api.POST("/api/v1/conversations/", { body: { title: "Hi" } }));
    expect(bodies).toEqual(['{"title":"Hi"}', '{"title":"Hi"}']);
  });
});

