import axe from "axe-core";

/**
 * Run the axe accessibility rules on a rendered component and return a list of
 * problems (empty means none). Colour contrast cannot be measured in jsdom,
 * so tokens.test.ts checks the palette numerically instead.
 */
export async function accessibilityProblems(container: Element) {
  const results = await axe.run(container, {
    rules: {
      "color-contrast": { enabled: false },
      region: { enabled: false }, // a lone component is not a whole page
    },
  });
  return results.violations.map(
    (v) =>
      `${v.id}: ${v.help} (${v.nodes.map((n) => n.target.join(" ")).join(", ")})`,
  );
}
