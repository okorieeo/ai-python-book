// Stop hook: Claude may not finish a turn while typecheck or tests fail.
// Exit code 2 keeps Claude working and sends stderr back to it.
import { readFileSync } from "node:fs";
import { spawnSync } from "node:child_process";

const input = JSON.parse(readFileSync(0, "utf8"));
if (input.stop_hook_active) process.exit(0); // already retrying once: never loop forever

// Skip the check on turns that did not touch source files (a pure question, for example).
const status = spawnSync("git", ["status", "--porcelain", "--", "src"], { encoding: "utf8" });
if (status.status === 0 && status.stdout.trim() === "") process.exit(0);

const checks = [
  ["typecheck", ["run", "typecheck"]],
  ["tests", ["test"]],
];
for (const [name, args] of checks) {
  const result = spawnSync("npm", args, { encoding: "utf8" });
  if (result.status !== 0) {
    const tail = `${result.stdout}\n${result.stderr}`.trim().split("\n").slice(-40).join("\n");
    console.error(`You are not done: \`npm ${args.join(" ")}\` failed (${name}). Fix the cause, then run it again.\n\n${tail}`);
    process.exit(2);
  }
}
process.exit(0);
