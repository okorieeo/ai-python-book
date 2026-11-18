import { describe, expect, it } from "vitest";
import { formatPrice, formatTokens } from "./format";
import { yearlyPriceCents } from "./plans";

describe("formatPrice", () => {
  it("turns integer cents into a currency string", () => {
    expect(formatPrice(1900)).toBe("$19.00");
    expect(formatPrice(0)).toBe("$0.00");
    expect(formatPrice(4999)).toBe("$49.99");
  });
});

describe("formatTokens", () => {
  it("uses K and M for large numbers", () => {
    expect(formatTokens(50_000)).toBe("50K tokens");
    expect(formatTokens(1_000_000)).toBe("1M tokens");
    expect(formatTokens(800)).toBe("800 tokens");
  });
});

describe("yearlyPriceCents", () => {
  it("charges ten months for twelve", () => {
    expect(yearlyPriceCents(1900)).toBe(19_000);
  });
});
