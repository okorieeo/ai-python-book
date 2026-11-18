// @vitest-environment node
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { contrastRatio } from "../../test/contrast";

const css = readFileSync(new URL("./globals.css", import.meta.url), "utf8");

/** Read the --name: #hex pairs inside a CSS block such as ":root { ... }". */
function tokens(selector: string): Record<string, string> {
  const block = css.match(new RegExp(`${selector}\\s*{([^}]*)}`))?.[1] ?? "";
  return Object.fromEntries(
    [...block.matchAll(/--([\w-]+):\s*(#[0-9a-fA-F]{6})/g)].map((m) => [
      m[1],
      m[2],
    ]),
  );
}

// [foreground token, background token, minimum ratio, what it is]
const textPairs: [string, string, number][] = [
  ["foreground", "background", 4.5],
  ["card-foreground", "card", 4.5],
  ["muted-foreground", "background", 4.5],
  ["muted-foreground", "muted", 4.5],
  ["foreground", "muted", 4.5],
  ["accent-foreground", "accent", 4.5],
  ["primary-foreground", "primary", 4.5],
  ["destructive-foreground", "destructive", 4.5],
  ["primary", "background", 4.5], // links and icons drawn in the primary colour
  ["destructive", "background", 4.5], // error messages
];
// Borders of inputs and focus rings must stand out from the page (WCAG 1.4.11).
const boundaryPairs: [string, string, number][] = [
  ["input", "background", 3],
  ["ring", "background", 3],
];

describe.each([":root", "\\.dark"])("colour tokens in %s", (selector) => {
  const t = tokens(selector);

  it("defines every token we check", () => {
    for (const [fg, bg] of [...textPairs, ...boundaryPairs]) {
      expect(t[fg], fg).toBeDefined();
      expect(t[bg], bg).toBeDefined();
    }
  });

  it.each(textPairs)(
    "%s on %s has contrast of at least %s:1",
    (fg, bg, min) => {
      expect(contrastRatio(t[fg], t[bg])).toBeGreaterThanOrEqual(min);
    },
  );

  it.each(boundaryPairs)("%s against %s has at least %s:1", (fg, bg, min) => {
    expect(contrastRatio(t[fg], t[bg])).toBeGreaterThanOrEqual(min);
  });
});

describe("the contrast helper", () => {
  it("knows the extremes", () => {
    expect(contrastRatio("#000000", "#ffffff")).toBeCloseTo(21, 0);
    expect(contrastRatio("#777777", "#777777")).toBe(1);
  });
});
