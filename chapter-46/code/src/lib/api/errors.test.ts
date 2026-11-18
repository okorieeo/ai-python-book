// @vitest-environment node
import { describe, expect, it } from "vitest";
import { ApiError, friendlyMessage, toApiError } from "./errors";

describe("toApiError", () => {
  it("reads the Chapter 8 envelope", () => {
    const error = toApiError(
      400,
      { error: { code: "validation_error", message: "Bad input", request_id: "req_1", fields: { email: ["Taken"] } } },
      new Headers(),
    );
    expect(error.code).toBe("validation_error");
    expect(error.requestId).toBe("req_1");
    expect(error.fields).toEqual({ email: ["Taken"] });
  });

  it("survives a body that is not an envelope (a proxy error page, say)", () => {
    const error = toApiError(502, "<html>Bad gateway</html>", new Headers());
    expect(error.code).toBe("http_502");
    expect(error.message).toBe("Request failed");
  });

  it("reads Retry-After and ignores garbage", () => {
    expect(toApiError(429, null, new Headers({ "Retry-After": "12" })).retryAfter).toBe(12);
    expect(toApiError(429, null, new Headers({ "Retry-After": "soon" })).retryAfter).toBeUndefined();
  });
});

describe("friendlyMessage", () => {
  it("never shows server text for a 500, only the request id", () => {
    const error = new ApiError({ status: 500, code: "server_error", message: "psycopg2.OperationalError: ...", requestId: "req_9" });
    const text = friendlyMessage(error);
    expect(text).toContain("req_9");
    expect(text).not.toContain("psycopg2");
  });

  it("tells the user how long to wait after a 429", () => {
    const error = new ApiError({ status: 429, code: "throttled", message: "x", retryAfter: 30 });
    expect(friendlyMessage(error)).toContain("30 seconds");
  });

  it("handles a network failure", () => {
    const error = new ApiError({ status: 0, code: "network_error", message: "x" });
    expect(friendlyMessage(error)).toMatch(/could not reach the server/i);
  });

  it("handles things that are not ApiErrors", () => {
    expect(friendlyMessage(new TypeError("boom"))).toBe("Something went wrong. Please try again.");
  });
});
