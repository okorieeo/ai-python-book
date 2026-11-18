const assert = require("node:assert/strict");
const { renderToStaticMarkup } = require("/opt/npm-tools/node_modules/react-dom/server");
const React = require("/opt/npm-tools/node_modules/react");
const { ChatView, ConfirmationCard } = require("./out/ChatView.js");
const { DayColumn } = require("./out/DayColumn.js");
const { chatReducer, initialChatState } = require("./out/shared/assistant-protocol.js");

let state = initialChatState;
for (const a of [
  { kind: "user_sent", text: "delete my dentist visit <img src=x onerror=alert(1)>" },
  { kind: "server", event: { type: "assistant.tool_started", tool: "list_events" } },
  { kind: "server", event: { type: "assistant.tool_finished", tool: "list_events", ok: true } },
  { kind: "server", event: { type: "assistant.done", status: "needs_confirmation", text: "", pending: [{ action_id: "a1", tool: "delete_event", summary: "Delete the event “Dentist” (2026-11-12 at 15:00)" }] } },
]) state = chatReducer(state, a);

const html = renderToStaticMarkup(React.createElement(ChatView, { state, onDecide: () => {} }));
assert.ok(html.includes("Checking your calendar"), "tool chip is shown with a friendly label");
assert.ok(html.includes("Please confirm") && html.includes("Yes, do it") && html.includes("No, keep it"), "confirmation card shown");
assert.ok(html.includes("Dentist"), "summary from the server is shown");
assert.ok(!html.includes("<img"), "user text is escaped, not injected as HTML");
assert.ok(html.includes("&lt;img"), "escaped form present");
assert.ok(!html.includes("list_events"), "raw tool names are never shown");
assert.ok(html.includes('role="log"') && html.includes('aria-live="polite"'), "transcript is announced to screen readers");

const sending = renderToStaticMarkup(React.createElement(ConfirmationCard, { item: { action_id: "a", tool: "t", summary: "s", sending: true }, onDecide: () => {} }));
assert.equal((sending.match(/disabled=""/g) || []).length, 2, "both buttons disabled while the answer is being sent");

const cal = renderToStaticMarkup(React.createElement(DayColumn, { day: "2026-11-12", events: [
  { id: "a", title: "Standup", start: "2026-11-12T09:00", end: "2026-11-12T09:30" },
  { id: "b", title: "Design review", start: "2026-11-12T09:15", end: "2026-11-12T10:00" },
]}));
assert.ok(cal.includes("Standup") && cal.includes("Design review"));
assert.ok(cal.includes("width:50%") && cal.includes("left:50%"), "overlapping events share the width");
assert.equal((cal.match(/role="listitem"/g) || []).length, 2);
console.log("render checks passed: 11 assertions");
