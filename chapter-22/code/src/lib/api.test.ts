import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, apiGet, buildQuery } from "./api";
import { setAccessToken } from "./auth";

afterEach(() => {
  vi.unstubAllGlobals();
  setAccessToken(null);
});

describe("buildQuery", () => {
  it("leaves out empty values so URLs stay clean", () => {
    expect(buildQuery({ page: 2, search: "", role: null, x: undefined })).toBe(
      "?page=2",
    );
    expect(buildQuery({})).toBe("");
    expect(buildQuery({ q: "a b&c" })).toBe("?q=a+b%26c"); // encoded safely
  });
});

describe("apiGet", () => {
  it("sends the token and parses the JSON", async () => {
    setAccessToken("abc");
    const fetchMock = vi.fn(
      async () => new Response('{"ok":true}', { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchMock);
    expect(await apiGet("/me")).toEqual({ ok: true });
    const [url, init] = fetchMock.mock.calls[0] as unknown as [
      string,
      RequestInit,
    ];
    expect(url).toBe("http://localhost:8000/api/v1/me");
    expect((init.headers as Record<string, string>).Authorization).toBe(
      "Bearer abc",
    );
  });

  it("turns the API's error shape into an ApiError", async () => {
    const body = { error: { code: "permission_denied", message: "No." } };
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify(body), { status: 403 })),
    );
    await expect(apiGet("/admin/users")).rejects.toMatchObject({
      status: 403,
      code: "permission_denied",
      message: "No.",
    });
    await expect(apiGet("/admin/users")).rejects.toBeInstanceOf(ApiError);
  });
});
