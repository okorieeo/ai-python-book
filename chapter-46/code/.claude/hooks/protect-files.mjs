// PreToolUse hook for Edit|Write. Exit code 2 blocks the edit and sends stderr to Claude.
import { readFileSync } from "node:fs";

const input = JSON.parse(readFileSync(0, "utf8"));
const filePath = String(input?.tool_input?.file_path ?? "").replaceAll("\\", "/");

const rules = [
  { test: (p) => p.endsWith("/src/lib/api/schema.d.ts"), why: "This file is generated. Change openapi/schema.yml (or the Django serializer) and run `npm run api:types`." },
  { test: (p) => /\/\.env(\.|$)/.test(p) && !p.endsWith(".env.example"), why: "Environment files hold secrets. Edit .env.example and ask the human to update the real file." },
  { test: (p) => p.endsWith("/package-lock.json"), why: "The lockfile is managed by npm. Run npm install instead of editing it." },
  { test: (p) => p.includes("/.git/"), why: "Never edit Git internals." },
];

const hit = rules.find((rule) => rule.test(filePath));
if (hit) {
  console.error(`Blocked: ${filePath}\n${hit.why}`);
  process.exit(2);
}
process.exit(0);
