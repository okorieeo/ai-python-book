// VERIFICATION ONLY. Starts the fixture app, installs the @playwright/test stand-in next to a COPY of the spec,
// runs it in real Chromium, and exits non-zero on failure.   tsx verification_only/run-e2e.mjs web/e2e/checkout.spec.ts
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { pathToFileURL, fileURLToPath } from "node:url";
import { startServer } from "../web/e2e/fixture-app/server.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const spec = path.resolve(process.argv[2]);
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "e2e-"));
const shimDir = path.join(tmp, "node_modules", "@playwright", "test");
fs.mkdirSync(shimDir, { recursive: true });
for (const f of ["package.json", "index.mjs"]) fs.copyFileSync(path.join(here, "playwright-test-shim", f), path.join(shimDir, f));
fs.copyFileSync(spec, path.join(tmp, path.basename(spec)));

const { port, close } = await startServer(0);
process.env.BASE_URL = `http://127.0.0.1:${port}`;
process.env.PLAYWRIGHT_LIB ??= "/opt/npm-tools/node_modules/playwright";
await import(pathToFileURL(path.join(tmp, path.basename(spec))).href);
const code = await globalThis.__pwRun();
close();
fs.rmSync(tmp, { recursive: true, force: true });
process.exit(code);
