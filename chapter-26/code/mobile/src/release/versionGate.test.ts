import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { compareVersions, isOlderThan, parseVersion } from "./version";
import { evaluateGate, type AppConfigResponse } from "./versionGate";

const policy = (over: Partial<AppConfigResponse> = {}): AppConfigResponse => ({
  min_version: "1.2.0",
  recommended_version: "1.4.0",
  store_url: "https://apps.apple.com/app/id1234567890",
  maintenance: false,
  message: "",
  ...over,
});

describe("parseVersion", () => {
  it("parses x.y.z", () => {
    assert.deepEqual(parseVersion("1.20.3"), [1, 20, 3]);
  });
  it("trims whitespace", () => {
    assert.deepEqual(parseVersion(" 2.0.0\n"), [2, 0, 0]);
  });
  for (const bad of ["1.2", "1.2.3.4", "v1.2.3", "1.2.x", "", "1.2.3-beta", "-1.0.0"]) {
    it(`rejects ${JSON.stringify(bad)}`, () => {
      assert.throws(() => parseVersion(bad));
    });
  }
});

describe("compareVersions", () => {
  it("compares numerically, not as text", () => {
    assert.equal(compareVersions("1.10.0", "1.9.0"), 1);
    assert.equal(compareVersions("1.9.0", "1.10.0"), -1);
  });
  it("is 0 for equal versions", () => {
    assert.equal(compareVersions("3.4.5", "3.4.5"), 0);
  });
  it("major beats minor beats patch", () => {
    assert.equal(compareVersions("2.0.0", "1.99.99"), 1);
    assert.equal(compareVersions("1.2.0", "1.1.99"), 1);
    assert.equal(compareVersions("1.2.4", "1.2.3"), 1);
  });
  it("isOlderThan is strict", () => {
    assert.equal(isOlderThan("1.2.0", "1.2.0"), false);
    assert.equal(isOlderThan("1.1.9", "1.2.0"), true);
  });
});

describe("evaluateGate", () => {
  it("lets a current version in", () => {
    assert.deepEqual(evaluateGate(policy(), "1.4.0"), { kind: "ok" });
    assert.deepEqual(evaluateGate(policy(), "2.0.0"), { kind: "ok" });
  });
  it("suggests an update below the recommended version", () => {
    const state = evaluateGate(policy(), "1.3.0");
    assert.equal(state.kind, "recommended");
  });
  it("blocks below the minimum version", () => {
    const state = evaluateGate(policy(), "1.1.9");
    assert.equal(state.kind, "blocked");
    if (state.kind === "blocked") assert.equal(state.reason, "outdated");
  });
  it("the minimum version itself is allowed", () => {
    assert.equal(evaluateGate(policy(), "1.2.0").kind, "recommended");
  });
  it("maintenance blocks everyone, even the newest version", () => {
    const state = evaluateGate(policy({ maintenance: true, message: "Back at 10:00" }), "9.9.9");
    assert.equal(state.kind, "blocked");
    if (state.kind === "blocked") {
      assert.equal(state.reason, "maintenance");
      assert.equal(state.message, "Back at 10:00");
    }
  });
  it("uses the server message when there is one", () => {
    const state = evaluateGate(policy({ message: "Security fix inside." }), "1.0.0");
    if (state.kind === "blocked") assert.equal(state.message, "Security fix inside.");
  });
  it("fails OPEN when there is no policy", () => {
    assert.deepEqual(evaluateGate(null, "0.0.1"), { kind: "ok" });
    assert.deepEqual(evaluateGate(undefined, "0.0.1"), { kind: "ok" });
  });
  it("fails OPEN when the policy is malformed", () => {
    assert.deepEqual(evaluateGate(policy({ min_version: "banana" }), "1.0.0"), { kind: "ok" });
    assert.deepEqual(evaluateGate(policy({ recommended_version: "" }), "1.0.0"), { kind: "ok" });
  });
  it("fails OPEN when the installed version is unreadable", () => {
    assert.deepEqual(evaluateGate(policy(), "not-a-version"), { kind: "ok" });
  });
});
