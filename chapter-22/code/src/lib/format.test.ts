import { describe, expect, it } from "vitest";

import { formatCompact, formatDay, formatNumber } from "./format";

describe("format", () => {
  it("shortens big numbers for axes and spells them out for tables", () => {
    expect(formatCompact(12400)).toBe("12.4K");
    expect(formatNumber(12400)).toBe("12,400");
  });

  it("shows a calendar day as that same day in every time zone", () => {
    expect(formatDay("2026-11-03")).toBe("Nov 3");
    expect(formatDay("2026-01-01")).toBe("Jan 1");
  });
});
