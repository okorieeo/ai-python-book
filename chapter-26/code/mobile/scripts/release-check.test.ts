import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, it } from "node:test";

import appConfig from "../app.config";
import { resolveVariant, VARIANTS } from "../config/variants";
import {
  checkRelease,
  hasErrors,
  resolveProfile,
  type AppConfigLike,
  type CheckInput,
  type EasJson,
} from "./checkRelease";

const GOOD_EAS: EasJson = {
  cli: { appVersionSource: "remote" },
  build: {
    development: { developmentClient: true, distribution: "internal", environment: "development" },
    preview: { distribution: "internal", channel: "preview", environment: "preview", android: { buildType: "apk" } },
    production: { channel: "production", environment: "production", autoIncrement: true },
  },
  submit: { production: { ios: { ascAppId: "1234567890" } } },
};

const cfg = (id: string): AppConfigLike => ({
  version: "1.0.0",
  runtimeVersion: { policy: "appVersion" },
  updates: { url: "https://u.expo.dev/5b1f3c1e-1111-4222-8333-444455556666" },
  ios: { bundleIdentifier: id, infoPlist: { ITSAppUsesNonExemptEncryption: false } },
  android: { package: id },
  extra: { eas: { projectId: "5b1f3c1e-1111-4222-8333-444455556666" } },
});

const good = (): CheckInput => ({
  eas: structuredClone(GOOD_EAS),
  appConfigs: {
    development: cfg("ng.acme.chat.dev"),
    preview: cfg("ng.acme.chat.preview"),
    production: cfg("ng.acme.chat"),
  },
});

const ids = (input: CheckInput) => checkRelease(input).map((f) => f.id);

describe("checkRelease on a good configuration", () => {
  it("finds nothing", () => {
    assert.deepEqual(checkRelease(good()), []);
  });
});

describe("checkRelease catches each mistake", () => {
  it("R001 local version source", () => {
    const i = good();
    i.eas.cli = { appVersionSource: "local" };
    assert.ok(ids(i).includes("R001"));
  });
  it("R002 no production profile", () => {
    const i = good();
    delete i.eas.build!.production;
    assert.deepEqual(ids(i), ["R001"].filter(() => false).concat(["R002"]));
  });
  it("R003 autoIncrement off", () => {
    const i = good();
    i.eas.build!.production.autoIncrement = false;
    assert.ok(ids(i).includes("R003"));
  });
  it("R004 to R006 production that is really a dev or internal build", () => {
    const i = good();
    Object.assign(i.eas.build!.production, { developmentClient: true, distribution: "internal", android: { buildType: "apk" } });
    const found = ids(i);
    for (const id of ["R004", "R005", "R006"]) assert.ok(found.includes(id), id);
  });
  it("R007 wrong environment", () => {
    const i = good();
    i.eas.build!.production.environment = "preview";
    assert.ok(ids(i).includes("R007"));
  });
  it("R008 missing production channel", () => {
    const i = good();
    delete i.eas.build!.production.channel;
    assert.ok(ids(i).includes("R008"));
  });
  it("R009 preview shares the production channel", () => {
    const i = good();
    i.eas.build!.preview.channel = "production";
    assert.ok(ids(i).includes("R009"));
  });
  it("R010 preview without a channel is only a warning", () => {
    const i = good();
    delete i.eas.build!.preview.channel;
    const f = checkRelease(i).find((x) => x.id === "R010");
    assert.equal(f?.severity, "warn");
    assert.equal(hasErrors(checkRelease(i)), false);
  });
  it("R011 secret in a committed env block", () => {
    const i = good();
    i.eas.build!.preview.env = { STRIPE_SECRET_KEY: "sk_live_x" };
    assert.ok(ids(i).includes("R011"));
  });
  it("R012 secret with the public prefix is reported once, as R012", () => {
    const i = good();
    i.eas.build!.preview.env = { EXPO_PUBLIC_OPENAI_API_KEY: "x" };
    const found = ids(i);
    assert.ok(found.includes("R012"));
    assert.ok(!found.includes("R011"));
  });
  it("a harmless env value is fine", () => {
    const i = good();
    i.eas.build!.preview.env = { EXPO_PUBLIC_API_URL: "https://api.acme.ng" };
    assert.deepEqual(checkRelease(i), []);
  });
  it("R014 missing identifiers", () => {
    const i = good();
    i.appConfigs.production = { ...cfg("x"), ios: {}, android: {} };
    assert.ok(ids(i).includes("R014"));
  });
  it("R016 placeholder identifier", () => {
    const i = good();
    i.appConfigs.production = cfg("com.example.aichat");
    assert.ok(ids(i).includes("R016"));
  });
  it("R017 bad version", () => {
    const i = good();
    i.appConfigs.production.version = "1.0";
    assert.ok(ids(i).includes("R017"));
  });
  it("R018 and R019 missing update wiring", () => {
    const i = good();
    delete i.appConfigs.production.runtimeVersion;
    i.appConfigs.production.updates = {};
    const found = ids(i);
    assert.ok(found.includes("R018") && found.includes("R019"));
  });
  it("R020 placeholder project id", () => {
    const i = good();
    i.appConfigs.production.extra = { eas: { projectId: "00000000-0000-0000-0000-000000000000" } };
    assert.ok(ids(i).includes("R020"));
  });
  it("R022 variants that share an identifier", () => {
    const i = good();
    i.appConfigs.preview = cfg("ng.acme.chat");
    assert.ok(ids(i).includes("R022"));
  });
  it("R023 placeholder ascAppId is a warning", () => {
    const i = good();
    i.eas.submit!.production.ios!.ascAppId = "REPLACE_WITH_APPLE_ID_NUMBER";
    const f = checkRelease(i).find((x) => x.id === "R023");
    assert.equal(f?.severity, "warn");
  });
  it("R024 and R025 API url", () => {
    const a = good();
    a.env = { EXPO_PUBLIC_API_URL: "http://api.acme.ng" };
    assert.ok(ids(a).includes("R024"));
    const b = good();
    b.env = { EXPO_PUBLIC_API_URL: "https://192.168.1.20:8000" };
    assert.ok(ids(b).includes("R025"));
    const c = good();
    c.env = { EXPO_PUBLIC_API_URL: "https://api.acme.ng" };
    assert.deepEqual(checkRelease(c), []);
  });
});

describe("resolveProfile", () => {
  it("inherits through extends", () => {
    const merged = resolveProfile(
      { a: { channel: "x", android: { buildType: "apk" } }, b: { extends: "a", environment: "preview" } },
      "b",
    );
    assert.equal(merged.channel, "x");
    assert.equal(merged.android?.buildType, "apk");
  });
  it("survives a circular extends", () => {
    resolveProfile({ a: { extends: "b" }, b: { extends: "a" } }, "a");
  });
});

describe("variants", () => {
  it("unset means development", () => {
    assert.equal(resolveVariant(undefined).name, "development");
    assert.equal(resolveVariant("").name, "development");
  });
  it("a typo stops the build", () => {
    assert.throws(() => resolveVariant("prod"), /Unknown APP_VARIANT/);
    assert.throws(() => resolveVariant("toString"), /Unknown APP_VARIANT/);
  });
  it("every variant has its own identifier and scheme", () => {
    const all = Object.values(VARIANTS);
    assert.equal(new Set(all.map((v) => v.bundleId)).size, all.length);
    assert.equal(new Set(all.map((v) => v.scheme)).size, all.length);
  });
});

describe("the files shipped with this chapter", () => {
  const root = resolve(__dirname, "..");
  const eas = JSON.parse(readFileSync(resolve(root, "eas.json"), "utf8")) as EasJson;

  const resolveAll = () => {
    const out: Record<string, AppConfigLike> = {};
    for (const name of Object.keys(VARIANTS)) {
      process.env.APP_VARIANT = name;
      out[name] = appConfig({ config: {} } as never) as AppConfigLike;
    }
    delete process.env.APP_VARIANT;
    return out;
  };

  it("app.config.ts resolves a different identity per variant", () => {
    const c = resolveAll();
    assert.equal(c.production.ios?.bundleIdentifier, "com.example.aichat");
    assert.equal(c.development.android?.package, "com.example.aichat.dev");
    assert.equal(c.preview.extra && (c.preview.extra as { variant?: string }).variant, "preview");
  });

  it("the starter files fail ONLY on placeholders you must replace", () => {
    const found = checkRelease({ eas, appConfigs: resolveAll() });
    const errorIds = found.filter((f) => f.severity === "error").map((f) => f.id).sort();
    assert.deepEqual([...new Set(errorIds)], ["R016", "R020"]);
    assert.deepEqual(found.filter((f) => f.severity === "warn").map((f) => f.id), ["R023"]);
  });

  it("the starter profiles pass every structural rule", () => {
    const structural = checkRelease({ eas, appConfigs: resolveAll() })
      .map((f) => f.id)
      .filter((id) => !["R016", "R020", "R023"].includes(id));
    assert.deepEqual(structural, []);
  });
});
