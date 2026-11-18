import axe from "axe-core";

// Runs axe-core on a rendered container and fails with a readable list of violations.
export async function expectNoA11yViolations(container: Element) {
  const results = await axe.run(container, { rules: { "color-contrast": { enabled: false } } });
  // jsdom has no layout, so contrast is checked in a real browser (46.7), not here.
  const summary = results.violations.map((v) => `${v.id}: ${v.help} (${v.nodes.length})`);
  expect(summary).toEqual([]);
}
