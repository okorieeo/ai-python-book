// VERIFICATION ONLY. NOT FOR YOUR PROJECT. Use real Jest there.
// The sandbox could not install Jest, so this stand-in maps the small part of Jest's API that Chapter 39's
// pure-logic tests use (describe/it/test/each, beforeEach, expect matchers, jest.fn) onto Node's built-in
// test runner. It shows the tests' logic is sound; it does not prove identical behaviour under Jest.
//   node --import tsx --import ./verification_only/jest-globals.mjs --test web/lib/*.test.ts
import assert from "node:assert/strict";
import * as nt from "node:test";
import { isDeepStrictEqual } from "node:util";

const fmt = (name, args) => { let i = 0; return name.replace(/%[sdipj]/g, () => String(typeof args[i] === "string" ? args[i++] : JSON.stringify(args[i++]))); };
const withEach = (fn) => { fn.each = (table) => (name, body) => table.forEach((row) => { const args = Array.isArray(row) ? row : [row]; fn(fmt(name, args), () => body(...args)); }); return fn; };

globalThis.describe = withEach((n, f) => nt.describe(n, f));
globalThis.it = withEach((n, f) => nt.it(n, f));
globalThis.test = globalThis.it;
globalThis.beforeEach = (f) => nt.beforeEach(f);
globalThis.afterEach = (f) => nt.afterEach(f);

const matchers = (received, negate = false) => {
  const check = (pass, msg) => { if (negate ? pass : !pass) throw new assert.AssertionError({ message: (negate ? "NOT " : "") + msg }); };
  return {
    toBe: (e) => check(Object.is(received, e), `expected ${JSON.stringify(received)} toBe ${JSON.stringify(e)}`),
    toEqual: (e) => check(isDeepStrictEqual(received, e), `expected ${JSON.stringify(received)} toEqual ${JSON.stringify(e)}`),
    toStrictEqual: (e) => check(isDeepStrictEqual(received, e), `expected ${JSON.stringify(received)} toStrictEqual ${JSON.stringify(e)}`),
    toBeTruthy: () => check(!!received, `expected ${received} truthy`),
    toBeFalsy: () => check(!received, `expected ${received} falsy`),
    toBeNull: () => check(received === null, `expected ${received} null`),
    toBeUndefined: () => check(received === undefined, `expected ${received} undefined`),
    toBeDefined: () => check(received !== undefined, `expected defined`),
    toContain: (e) => check(received.includes(e), `expected ${JSON.stringify(received)} to contain ${JSON.stringify(e)}`),
    toHaveLength: (n) => check(received.length === n, `expected length ${received.length} toBe ${n}`),
    toMatch: (re) => check(typeof re === "string" ? received.includes(re) : re.test(received), `expected ${JSON.stringify(received)} toMatch ${re}`),
    toBeGreaterThan: (n) => check(received > n, `expected ${received} > ${n}`),
    toBeLessThan: (n) => check(received < n, `expected ${received} < ${n}`),
    toBeCloseTo: (n, d = 2) => check(Math.abs(received - n) < 10 ** -d / 2, `expected ${received} close to ${n}`),
    toHaveBeenCalledTimes: (n) => check(received.mock.calls.length === n, `expected ${n} calls, got ${received.mock.calls.length}`),
    toHaveBeenCalledWith: (...a) => check(received.mock.calls.some((c) => isDeepStrictEqual(c, a)), `expected a call with ${JSON.stringify(a)}`),
    toThrow: (e) => {
      let threw = null;
      try { received(); } catch (err) { threw = err; }
      const ok = threw !== null && (e === undefined || (typeof e === "string" ? threw.message.includes(e) : e instanceof RegExp ? e.test(threw.message) : threw instanceof e));
      check(ok, `expected function to throw ${e ?? ""}${threw ? ` (threw: ${threw.message})` : " (did not throw)"}`);
    },
  };
};

globalThis.expect = (received) => {
  const m = matchers(received);
  m.not = matchers(received, true);
  m.resolves = new Proxy({}, { get: (_, k) => async (...a) => matchers(await received)[k](...a) });
  m.rejects = {
    toThrow: async (e) => {
      let threw = null;
      try { await received; } catch (err) { threw = err; }
      matchers(() => { if (threw) throw threw; }).toThrow(e);
    },
  };
  return m;
};

globalThis.jest = {
  fn: (impl = () => undefined) => {
    const f = (...args) => { f.mock.calls.push(args); return f._impl(...args); };
    f.mock = { calls: [] };
    f._impl = impl;
    f.mockReturnValue = (v) => { f._impl = () => v; return f; };
    f.mockResolvedValue = (v) => { f._impl = async () => v; return f; };
    f.mockImplementation = (i) => { f._impl = i; return f; };
    return f;
  },
};
