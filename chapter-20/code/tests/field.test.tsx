import assert from "node:assert/strict";
import { test } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { Field, FormError } from "../components/forms/Field";

test("label, input, hint and error are wired together for screen readers", () => {
  const html = renderToStaticMarkup(<Field label="Email" type="email" hint="We never share it." error="Enter an email like name@example.com." />);
  const id = /<label for="([^"]+)">Email<\/label>/.exec(html)?.[1];
  assert.ok(id, "the label points at the input");
  assert.match(html, new RegExp(`<input id="${id.replace(/[:]/g, "\\:")}"`));
  assert.match(html, /aria-invalid="true"/);
  const describedBy = /aria-describedby="([^"]+)"/.exec(html)?.[1].split(" ") ?? [];
  assert.equal(describedBy.length, 2);
  for (const target of describedBy) assert.ok(html.includes(`id="${target}"`), `${target} exists`);
  assert.match(html, /<p id="[^"]+-error" role="alert"[^>]*>Enter an email like name@example.com\.<\/p>/);
});

test("without an error there is no aria-invalid and no alert", () => {
  const html = renderToStaticMarkup(<Field label="Name" />);
  assert.doesNotMatch(html, /aria-invalid/);
  assert.doesNotMatch(html, /role="alert"/);
  assert.doesNotMatch(html, /aria-describedby/);
});

test("each field gets its own unique id", () => {
  const html = renderToStaticMarkup(<><Field label="One" /><Field label="Two" /></>);
  const ids = [...html.matchAll(/<input id="([^"]+)"/g)].map((m) => m[1]);
  assert.equal(new Set(ids).size, 2);
});

test("FormError renders an alert only when there is a message", () => {
  assert.equal(renderToStaticMarkup(<FormError message={null} />), "");
  assert.match(renderToStaticMarkup(<FormError message="Incorrect email or password." />), /role="alert"[^>]*>Incorrect email or password\./);
});
