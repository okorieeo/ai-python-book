import { formatMoney, formatTokens } from "./format";

describe("formatMoney", () => {
  it.each([
    [1999, "USD", "$19.99"],
    [0, "USD", "$0.00"],
    [5, "USD", "$0.05"],
    [100_000_000, "USD", "$1,000,000.00"],
    [500, "JPY", "¥500"],
  ])("formats %i minor units of %s as %s", (minor: number, currency: string, expected: string) => {
    expect(formatMoney(minor, currency)).toBe(expected);
  });

  it("treats the amount as kobo for naira, without asserting on the locale-specific symbol", () => {
    // The symbol and spacing for NGN differ between ICU versions and locales, so check the NUMBER, not the glyph.
    const text = formatMoney(150_000, "NGN");
    expect(text).toMatch(/1,500\.00/);
  });

  it("rejects fractional minor units: money is never a float", () => {
    expect(() => formatMoney(19.99, "USD")).toThrow("integer");
  });

  it("rejects an unknown currency instead of printing nonsense", () => {
    expect(() => formatMoney(100, "NOT-A-CURRENCY")).toThrow();
  });
});

describe("formatTokens", () => {
  it.each([[0, "0"], [999, "999"], [1_000, "1K"], [1_234, "1.2K"], [15_000, "15K"], [1_500_000, "1.5M"], [2_000_000, "2M"]])(
    "%i becomes %s",
    (n: number, expected: string) => expect(formatTokens(n)).toBe(expected),
  );

  it("rejects negatives and NaN", () => {
    expect(() => formatTokens(-1)).toThrow();
    expect(() => formatTokens(Number.NaN)).toThrow();
  });
});
