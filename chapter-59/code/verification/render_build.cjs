const ts = require("/opt/npm-tools/node_modules/typescript");
const fs = require("fs"), path = require("path");
const root = "/home/claude/ch59/code";
const files = {
  "shared/assistant-protocol.js": "packages/shared/src/assistant-protocol.ts",
  "shared/calendar-layout.js": "packages/shared/src/calendar-layout.ts",
  "ChatView.js": "web/components/assistant/ChatView.tsx",
  "DayColumn.js": "web/components/calendar/DayColumn.tsx",
};
for (const [out, src] of Object.entries(files)) {
  let code = fs.readFileSync(path.join(root, src), "utf8");
  let js = ts.transpileModule(code, { compilerOptions: { module: "CommonJS", target: "ES2022", jsx: "react-jsx" } }).outputText;
  js = js.replace(/@app\/shared\/assistant-protocol/g, "./shared/assistant-protocol.js")
         .replace(/@app\/shared\/calendar-layout/g, "./shared/calendar-layout.js")
         .replace(/\.\/assistant-protocol\.ts/g, "./assistant-protocol.js")
         .replace(/\.\/calendar-layout\.ts/g, "./calendar-layout.js");
  fs.mkdirSync(path.dirname(path.join("out", out)), { recursive: true });
  fs.writeFileSync(path.join("out", out), js);
}
console.log("built");
