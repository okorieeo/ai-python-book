/**
 * Run: npx tsx scripts/release-check.ts
 * Exits 1 when there is at least one error, so CI stops before a bad release.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import appConfig from "../app.config";
import { VARIANTS } from "../config/variants";
import { checkRelease, hasErrors, type AppConfigLike, type EasJson } from "./checkRelease";

const root = resolve(__dirname, "..");
const eas = JSON.parse(readFileSync(resolve(root, "eas.json"), "utf8")) as EasJson;

// Resolve the app config once per variant, the same way Expo does at build time.
const appConfigs: Record<string, AppConfigLike> = {};
const previous = process.env.APP_VARIANT;
for (const name of Object.keys(VARIANTS)) {
  process.env.APP_VARIANT = name;
  appConfigs[name] = appConfig({ config: {} } as never) as AppConfigLike;
}
if (previous === undefined) delete process.env.APP_VARIANT;
else process.env.APP_VARIANT = previous;

const findings = checkRelease({ eas, appConfigs, env: process.env });

for (const f of findings) {
  console.log(`${f.severity === "error" ? "ERROR" : "warn "} ${f.id}  ${f.message}`);
}
const errors = findings.filter((f) => f.severity === "error").length;
const warnings = findings.length - errors;
console.log(`\n${errors} error(s), ${warnings} warning(s)`);
process.exit(hasErrors(findings) ? 1 : 0);
