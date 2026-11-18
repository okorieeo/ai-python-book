import assert from "node:assert/strict";
import { test, describe } from "node:test";
import { ApiError, errorFromResponse, isRetryable, messageForError } from "../lib/api/errors";
import { buildQuery } from "../lib/api/query-string";
import { decodeJwtPayload, isExpiringSoon, tokenExpiresAt } from "../lib/auth/jwt";
import { decideRedirect, safeNextPath } from "../lib/auth/redirects";
import { clearCookie, parseCookies, serializeCookie } from "../lib/bff/cookies";
import { conversationSchema, loginSchema, signupSchema } from "../lib/forms/schemas";
import { mapApiErrorToForm } from "../lib/forms/server-errors";
import { isValidEmail, passwordProblems } from "../lib/forms/validators";
import { flattenPages, prependToFirstPage, removeItem, replaceItem, uniqueById } from "../lib/query/cache-updates";
import { retryDelay, shouldRetry } from "../lib/query/retry";
import { clearDraft, getDraft, setDraft } from "../lib/state/drafts";

function fakeJwt(payload: object): string {
  const encode = (value: object) => Buffer.from(JSON.stringify(value)).toString("base64url");
  return `${encode({ alg: "HS256", typ: "JWT" })}.${encode(payload)}.signature`;
}

describe("jwt helpers", () => {
  test("decodes the payload and the expiry without verifying", () => {
    const token = fakeJwt({ sub: "usr_1", exp: 1_800_000_000, name: "Zo\u00eb \u2603" });
    assert.equal(decodeJwtPayload(token)?.sub, "usr_1");
    assert.equal(decodeJwtPayload(token)?.name, "Zo\u00eb \u2603");     // UTF-8 survives
    assert.equal(tokenExpiresAt(token), 1_800_000_000);
  });
  test("garbage is handled, never thrown", () => {
    for (const bad of ["", "abc", "a.b", "a.b.c", "a.!!!.c", `x.${Buffer.from("[1]").toString("base64url")}.z`]) {
      assert.equal(decodeJwtPayload(bad), null, bad);
    }
    assert.equal(tokenExpiresAt(fakeJwt({ sub: "x" })), null);
  });
  test("isExpiringSoon respects the skew", () => {
    const token = fakeJwt({ exp: 1000 });
    assert.equal(isExpiringSoon(token, 900, 30), false);   // 100 s left
    assert.equal(isExpiringSoon(token, 975, 30), true);    // 25 s left
    assert.equal(isExpiringSoon(token, 1000, 0), true);    // expired
    assert.equal(isExpiringSoon(undefined, 0), true);
    assert.equal(isExpiringSoon("not-a-token", 0), true);
  });
});

describe("cookies", () => {
  test("parseCookies handles spaces, encoding, duplicates and junk", () => {
    assert.deepEqual(parseCookies("a=1; b=hello%20world;  c=x=y; novalue; =oops; a=2"), { a: "1", b: "hello world", c: "x=y" });
    assert.deepEqual(parseCookies(null), {});
    assert.deepEqual(parseCookies("bad=%E0%A4%A"), { bad: "%E0%A4%A" });
  });
  test("session cookies are HttpOnly, SameSite=Lax, and Secure only when asked", () => {
    const plain = serializeCookie("ai_access", "tok/en+1", { maxAgeSeconds: 900.7, secure: false });
    assert.match(plain, /^ai_access=tok%2Fen%2B1; Path=\/; Max-Age=900; HttpOnly; SameSite=Lax$/);
    assert.ok(serializeCookie("a", "b", { maxAgeSeconds: 1, secure: true }).endsWith("; Secure"));
    assert.match(clearCookie("ai_access", true), /Max-Age=0/);
    assert.match(serializeCookie("a", "b", { maxAgeSeconds: -50, secure: false }), /Max-Age=0/);
  });
});

describe("api errors", () => {
  test("parses the standard error format", async () => {
    const response = new Response(JSON.stringify({ error: { code: "validation_error", message: "Bad.", details: { title: ["Required."], odd: "text" } }, request_id: "req_1" }),
      { status: 400, headers: { "retry-after": "7" } });
    const error = await errorFromResponse(response);
    assert.deepEqual([error.status, error.code, error.requestId, error.retryAfter], [400, "validation_error", "req_1", 7]);
    assert.deepEqual(error.details, { title: ["Required."], odd: ["text"] });
  });
  test("survives HTML, empty and weird bodies", async () => {
    const html = await errorFromResponse(new Response("<h1>Bad gateway</h1>", { status: 502, headers: { "x-request-id": "req_h" } }));
    assert.deepEqual([html.code, html.requestId], ["internal_error", "req_h"]);
    assert.equal((await errorFromResponse(new Response(null, { status: 404 }))).code, "not_found");
    assert.equal((await errorFromResponse(new Response("[]", { status: 401 }))).code, "not_authenticated");
    assert.equal((await errorFromResponse(new Response(JSON.stringify({ error: "nope" }), { status: 429 }))).code, "rate_limited");
  });
  test("friendly messages and retry rules", () => {
    assert.match(messageForError(new ApiError({ status: 0, code: "network_error", message: "x" })), /couldn\u2019t reach/);
    assert.match(messageForError(new ApiError({ status: 500, code: "weird", message: "stack trace here" })), /Something went wrong/);
    assert.equal(messageForError(new ApiError({ status: 400, code: "weird", message: "Custom server text" })), "Custom server text");
    assert.equal(isRetryable(new ApiError({ status: 0, code: "network_error", message: "" })), true);
    assert.equal(isRetryable(new ApiError({ status: 503, code: "upstream_unavailable", message: "" })), true);
    assert.equal(isRetryable(new ApiError({ status: 404, code: "not_found", message: "" })), false);
    assert.equal(isRetryable(new ApiError({ status: 401, code: "not_authenticated", message: "" })), false);
    assert.equal(isRetryable(new Error("boom")), false);
  });
  test("TanStack retry helpers", () => {
    const network = new ApiError({ status: 0, code: "network_error", message: "" });
    assert.deepEqual([0, 1, 2, 3].map((n) => shouldRetry(n, network)), [true, true, false, false]);
    assert.equal(shouldRetry(0, new ApiError({ status: 400, code: "validation_error", message: "" })), false);
    assert.deepEqual([0, 1, 2, 5, 9].map(retryDelay), [500, 1000, 2000, 8000, 8000]);
  });
});

describe("query strings", () => {
  test("skips empty values and joins arrays", () => {
    assert.equal(buildQuery({ limit: 20, cursor: null, q: "", status: ["ready", "processing"], empty: [], flag: false }), "?limit=20&status=ready%2Cprocessing&flag=false");
    assert.equal(buildQuery({}), "");
    assert.equal(buildQuery({ q: "a b&c=d" }), "?q=a+b%26c%3Dd");
  });
});

describe("redirects", () => {
  test("safeNextPath blocks open redirects", () => {
    const attacks = ["//evil.example", "https://evil.example/x", "/\\evil.example", "javascript:alert(1)", "/%2F%2Fevil.example", "/ok/../..//evil", "\n/chat", "chat", "/a\u0000b", "http:evil.example", "/" + "x".repeat(400)];
    for (const attack of attacks) {
      const result = safeNextPath(attack);
      assert.ok(result === "/chat" || (result.startsWith("/") && !result.startsWith("//") && !result.includes("://")), `${attack} -> ${result}`);
    }
    assert.equal(safeNextPath("//evil.example"), "/chat");
    assert.equal(safeNextPath("https://evil.example"), "/chat");
    assert.equal(safeNextPath("/%2F%2Fevil.example"), "/chat");
  });
  test("safeNextPath keeps legitimate paths", () => {
    assert.equal(safeNextPath("/chat/abc?x=1#top"), "/chat/abc?x=1#top");
    assert.equal(safeNextPath("/settings"), "/settings");
    assert.equal(safeNextPath(null), "/chat");
    assert.equal(safeNextPath(undefined, "/home"), "/home");
  });
  test("decideRedirect protects pages and bounces logged-in users off the login page", () => {
    assert.equal(decideRedirect("/chat", "", false), "/login?next=%2Fchat");
    assert.equal(decideRedirect("/chat/42", "?tab=a", false), "/login?next=%2Fchat%2F42%3Ftab%3Da");
    assert.equal(decideRedirect("/chat", "", true), null);
    assert.equal(decideRedirect("/login", "", true), "/chat");
    assert.equal(decideRedirect("/login", "", false), null);
    assert.equal(decideRedirect("/", "", false), null);
    assert.equal(decideRedirect("/pricing", "", false), null);
    assert.equal(decideRedirect("/chatty", "", false), null);          // a prefix match must respect path boundaries
    assert.equal(decideRedirect("/billing/invoices", "", false), "/login?next=%2Fbilling%2Finvoices");
  });
});

describe("validators and schemas", () => {
  test("emails", () => {
    for (const ok of ["ada@example.com", " bo+tag@sub.example.org "]) assert.equal(isValidEmail(ok), true, ok);
    for (const bad of ["", "ada", "ada@", "@example.com", "ada@example", "a b@example.com", "a@b.c", "x".repeat(250) + "@example.com"]) assert.equal(isValidEmail(bad), false, bad);
  });
  test("password problems", () => {
    assert.deepEqual(passwordProblems("correct-horse-battery", "ada@example.com"), []);
    assert.deepEqual(passwordProblems("short"), ["Use at least 8 characters."]);
    assert.ok(passwordProblems("12345678").length >= 2);
    assert.deepEqual(passwordProblems("Password"), ["That password is too common."]);
    assert.deepEqual(passwordProblems("ada-lovelace-1", "ada.lovelace@example.com").length, 0);
    assert.deepEqual(passwordProblems("xxada.lovelacexx", "ada.lovelace@example.com"), ["Don\u2019t include your email name in the password."]);
  });
  test("login schema trims the email and explains each problem", () => {
    const ok = loginSchema.safeParse({ email: "  ada@example.com ", password: "x" });
    assert.ok(ok.success && ok.data.email === "ada@example.com");
    const bad = loginSchema.safeParse({ email: "nope", password: "" });
    assert.ok(!bad.success);
    const messages = Object.fromEntries(bad.error.issues.map((i) => [i.path.join("."), i.message]));
    assert.deepEqual(messages, { email: "Enter an email like name@example.com.", password: "Enter your password." });
  });
  test("signup schema checks the password rules and the confirmation", () => {
    const good = { name: " Ada ", email: "ada@example.com", password: "correct-horse-battery", confirmPassword: "correct-horse-battery" };
    const parsed = signupSchema.safeParse(good);
    assert.ok(parsed.success && parsed.data.name === "Ada");
    const bad = signupSchema.safeParse({ ...good, password: "short", confirmPassword: "different" });
    assert.ok(!bad.success);
    const byField = bad.error.issues.map((i) => `${i.path.join(".")}: ${i.message}`);
    assert.deepEqual(byField, ["password: Use at least 8 characters.", "confirmPassword: Passwords do not match."]);
    assert.ok(!signupSchema.safeParse({ ...good, name: "" }).success);
  });
  test("conversation schema", () => {
    assert.ok(conversationSchema.safeParse({ title: "  Trip plan " }).success);
    assert.ok(!conversationSchema.safeParse({ title: "   " }).success);
    assert.ok(!conversationSchema.safeParse({ title: "x".repeat(201) }).success);
  });
});

describe("server errors mapped to forms", () => {
  const fields = ["email", "password", "name"] as const;
  test("field errors stay with their fields, the rest go to the form", () => {
    const error = new ApiError({ status: 400, code: "validation_error", message: "Bad", details: { email: ["Taken."], non_field_errors: ["Try later."], unknown: ["Odd."] } });
    assert.deepEqual(mapApiErrorToForm(error, fields), { fieldErrors: [{ field: "email", message: "Taken." }], formError: "Try later. Odd." });
  });
  test("only field errors means no form-level message", () => {
    const error = new ApiError({ status: 400, code: "validation_error", message: "Bad", details: { password: ["Too short.", "Too common."] } });
    assert.deepEqual(mapApiErrorToForm(error, fields), { fieldErrors: [{ field: "password", message: "Too short. Too common." }], formError: null });
  });
  test("other errors become friendly form messages", () => {
    assert.equal(mapApiErrorToForm(new ApiError({ status: 401, code: "authentication_failed", message: "x" }), fields).formError, "Incorrect email or password.");
    assert.match(mapApiErrorToForm(new ApiError({ status: 0, code: "network_error", message: "x" }), fields).formError!, /couldn\u2019t reach/);
    assert.match(mapApiErrorToForm(new Error("weird"), fields).formError!, /Something went wrong/);
    assert.match(mapApiErrorToForm(new ApiError({ status: 400, code: "validation_error", message: "Bad", details: {} }), fields).formError!, /Bad/);
  });
});

describe("optimistic cache updates", () => {
  const page = (ids: string[], next: string | null) => ({ results: ids.map((id) => ({ id, title: id })), next });
  const data = { pages: [page(["a", "b"], "c1"), page(["c"], null)], pageParams: [null, "c1"] };
  test("prepend puts the item first and never mutates", () => {
    const frozen = structuredClone(data);
    const next = prependToFirstPage(data, { id: "new", title: "New" });
    assert.deepEqual(flattenPages(next).map((x) => x.id), ["new", "a", "b", "c"]);
    assert.deepEqual(data, frozen);
    assert.deepEqual(flattenPages(prependToFirstPage(undefined, { id: "n", title: "N" })).map((x) => x.id), ["n"]);
    assert.deepEqual(flattenPages(prependToFirstPage(data, { id: "a", title: "A again" })).map((x) => x.title), ["A again", "b", "c"]);
  });
  test("replace, remove and unique", () => {
    assert.deepEqual(flattenPages(replaceItem(data, "b", { id: "b2", title: "B2" })).map((x) => x.id), ["a", "b2", "c"]);
    assert.deepEqual(flattenPages(removeItem(data, "a")).map((x) => x.id), ["b", "c"]);
    assert.equal(removeItem(undefined, "a"), undefined);
    assert.deepEqual(uniqueById([{ id: "1" }, { id: "2" }, { id: "1" }]), [{ id: "1" }, { id: "2" }]);
    assert.deepEqual(flattenPages(undefined), []);
  });
});

describe("composer drafts", () => {
  test("saving, reading, clearing and trimming", () => {
    let drafts = setDraft({}, "c1", "hello", 1);
    assert.equal(getDraft(drafts, "c1"), "hello");
    drafts = setDraft(drafts, "c1", "   ", 2);                       // blank text removes the draft
    assert.equal(getDraft(drafts, "c1"), "");
    assert.equal(getDraft(clearDraft(setDraft({}, "c9", "x", 1), "c9"), "c9"), "");
    assert.equal(getDraft(setDraft({}, "c1", "x".repeat(9000), 1), "c1").length, 8000);
  });
  test("only the most recent drafts are kept", () => {
    let drafts = {};
    for (let i = 0; i < 25; i++) drafts = setDraft(drafts, `c${i}`, `text ${i}`, i, 20);
    assert.equal(Object.keys(drafts).length, 20);
    assert.equal(getDraft(drafts, "c24"), "text 24");
    assert.equal(getDraft(drafts, "c0"), "");
  });
});
