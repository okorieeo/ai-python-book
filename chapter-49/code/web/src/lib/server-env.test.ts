import { describe, expect, it } from "vitest";
import { apiInternalUrl } from "./server-env";

describe("apiInternalUrl", () => {
  it("uses the configured URL and trims trailing slashes", () => {
    expect(apiInternalUrl({ API_INTERNAL_URL: "http://backend:8000/" })).toBe("http://backend:8000");
  });

  it("falls back to localhost only outside production", () => {
    expect(apiInternalUrl({ NODE_ENV: "development" })).toBe("http://localhost:8000");
  });

  it("regression: production without API_INTERNAL_URL fails loudly instead of using localhost", () => {
    expect(() => apiInternalUrl({ NODE_ENV: "production" })).toThrow(/API_INTERNAL_URL is not set/);
  });
});
