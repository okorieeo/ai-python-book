import { describe, expect, it } from "vitest";
import { isNearBottom } from "./stick-to-bottom";

describe("isNearBottom", () => {
  it("is true at the very bottom", () => {
    expect(isNearBottom({ scrollTop: 600, scrollHeight: 1000, clientHeight: 400 })).toBe(true);
  });
  it("is true within the threshold (a few lines up)", () => {
    expect(isNearBottom({ scrollTop: 530, scrollHeight: 1000, clientHeight: 400 })).toBe(true);
  });
  it("is false when the reader scrolled up to read", () => {
    expect(isNearBottom({ scrollTop: 100, scrollHeight: 1000, clientHeight: 400 })).toBe(false);
  });
  it("is true when everything fits without scrolling", () => {
    expect(isNearBottom({ scrollTop: 0, scrollHeight: 300, clientHeight: 400 })).toBe(true);
  });
  it("respects a custom threshold", () => {
    expect(isNearBottom({ scrollTop: 500, scrollHeight: 1000, clientHeight: 400 }, 50)).toBe(false);
  });
});
