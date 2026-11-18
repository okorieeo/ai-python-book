// VERIFICATION ONLY. NOT FOR YOUR PROJECT. Use the real @playwright/test there.
// @playwright/test could not be installed in the sandbox, but the playwright LIBRARY and a real Chromium were
// available. This stand-in provides `test`, `test.beforeEach`, `test.describe` and the web-first `expect`
// matchers the chapter's spec uses, on top of the real library, so the spec drives a real browser. It does not
// reproduce the real runner's retries, parallelism, reporters or trace viewer.
import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
const pw = require(process.env.PLAYWRIGHT_LIB || "playwright");

const reg = (globalThis.__pw ??= { tests: [], hooks: [], prefix: [] });
const norm = (s) => String(s).replace(/\s+/g, " ").trim();

export const test = (title, fn) => reg.tests.push({ title: [...reg.prefix, title].join(" > "), scope: reg.prefix.join(" > "), fn });
test.describe = (name, fn) => { reg.prefix.push(name); fn(); reg.prefix.pop(); };
test.beforeEach = (fn) => reg.hooks.push({ scope: reg.prefix.join(" > "), fn });

const TIMEOUT = 5000;
async function poll(check, negate, describe) {
  const end = Date.now() + TIMEOUT;
  let last = "";
  for (;;) {
    try { const r = await check(); last = r.detail; if (r.pass !== negate) return; } catch (e) { last = String(e.message).split("\n")[0]; }
    if (Date.now() > end) throw new Error(`expect(${describe})${negate ? ".not" : ""} timed out after ${TIMEOUT}ms. ${last}`);
    await new Promise((r) => setTimeout(r, 100));
  }
}
const textMatches = (actual, expected, exact) => expected instanceof RegExp ? expected.test(actual) : exact ? norm(actual) === norm(expected) : norm(actual).includes(norm(expected));

function matchers(actual, negate) {
  const isLocator = actual && typeof actual.waitFor === "function";
  const isPage = actual && typeof actual.goto === "function";
  const plain = (pass, msg) => { if (pass === negate) throw new Error(`${negate ? "not " : ""}${msg}`); };
  const m = {
    toBeVisible: () => poll(async () => ({ pass: await actual.isVisible(), detail: "not visible" }), negate, "locator"),
    toBeHidden: () => poll(async () => ({ pass: !(await actual.isVisible()), detail: "still visible" }), negate, "locator"),
    toBeEnabled: () => poll(async () => ({ pass: await actual.isEnabled(), detail: "not enabled" }), negate, "locator"),
    toBeDisabled: () => poll(async () => ({ pass: await actual.isDisabled(), detail: "not disabled" }), negate, "locator"),
    toHaveText: (e) => poll(async () => { const t = (await actual.textContent()) ?? ""; return { pass: textMatches(t, e, true), detail: `text was ${JSON.stringify(norm(t))}` }; }, negate, "locator"),
    toContainText: (e) => poll(async () => { const t = (await actual.textContent()) ?? ""; return { pass: textMatches(t, e, false), detail: `text was ${JSON.stringify(norm(t))}` }; }, negate, "locator"),
    toHaveURL: (e) => poll(async () => { const u = actual.url(); return { pass: e instanceof RegExp ? e.test(u) : u === e || u.endsWith(e), detail: `url was ${u}` }; }, negate, "page"),
    toBe: (e) => plain(Object.is(actual, e), `expected ${JSON.stringify(actual)} to be ${JSON.stringify(e)}`),
    toEqual: (e) => plain(JSON.stringify(actual) === JSON.stringify(e), `expected ${JSON.stringify(actual)} toEqual ${JSON.stringify(e)}`),
    toHaveLength: (n) => plain(actual.length === n, `expected length ${actual.length} to be ${n}`),
    toBeTruthy: () => plain(!!actual, `expected ${actual} truthy`),
  };
  if (!isLocator && !isPage) for (const k of ["toBeVisible", "toBeHidden", "toBeEnabled", "toBeDisabled", "toHaveText", "toContainText", "toHaveURL"]) delete m[k];
  return m;
}
export const expect = (actual) => Object.assign(matchers(actual, false), { not: matchers(actual, true) });

globalThis.__pwRun = async () => {
  const baseURL = process.env.BASE_URL;
  const browser = await pw.chromium.launch();
  let passed = 0, failed = 0;
  for (const t of reg.tests) {
    const context = await browser.newContext({ baseURL });
    const request = await pw.request.newContext({ baseURL });
    const fixtures = { page: await context.newPage(), request, context, baseURL, browser };
    try {
      for (const h of reg.hooks) if (t.scope.startsWith(h.scope)) await h.fn(fixtures);
      await t.fn(fixtures);
      passed++; console.log(`  ok   ${t.title}`);
    } catch (e) {
      failed++; console.log(`  FAIL ${t.title}\n       ${String(e.message).split("\n").slice(0, 3).join("\n       ")}`);
    }
    await context.close(); await request.dispose();
  }
  await browser.close();
  console.log(`\n${passed} passed, ${failed} failed`);
  return failed ? 1 : 0;
};
