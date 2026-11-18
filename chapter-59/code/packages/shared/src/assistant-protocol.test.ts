import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { chatReducer, describeTool, initialChatState, type ChatAction, type ChatState } from "./assistant-protocol.ts";

const play = (actions: ChatAction[], from: ChatState = initialChatState): ChatState => actions.reduce(chatReducer, from);
const server = (event: Extract<ChatAction, { kind: "server" }>["event"]): ChatAction => ({ kind: "server", event });

describe("chatReducer", () => {
  it("adds the person's message and goes busy", () => {
    const s = play([{ kind: "user_sent", text: "hi" }]);
    assert.equal(s.busy, true);
    assert.deepEqual(s.items.map((i) => [i.role, i.text]), [["user", "hi"]]);
  });

  it("streams text into one assistant item", () => {
    const s = play([
      { kind: "user_sent", text: "hi" },
      server({ type: "assistant.text_delta", text: "Hel" }),
      server({ type: "assistant.text_delta", text: "lo" }),
    ]);
    assert.equal(s.items.length, 2);
    assert.equal(s.items[1]!.text, "Hello");
    assert.equal(s.items[1]!.streaming, true);
  });

  it("final text replaces narration streamed between tool calls", () => {
    const s = play([
      { kind: "user_sent", text: "what's tomorrow?" },
      server({ type: "assistant.text_delta", text: "Let me check." }),
      server({ type: "assistant.tool_started", tool: "list_events" }),
      server({ type: "assistant.tool_finished", tool: "list_events", ok: true }),
      server({ type: "assistant.done", status: "done", text: "You have a dentist visit at 15:00.", pending: [] }),
    ]);
    const reply = s.items[1]!;
    assert.equal(reply.text, "You have a dentist visit at 15:00.");
    assert.equal(reply.streaming, false);
    assert.deepEqual(reply.tools, [{ tool: "list_events", state: "done" }]);
    assert.equal(s.busy, false);
  });

  it("marks a failed tool", () => {
    const s = play([
      server({ type: "assistant.tool_started", tool: "create_event" }),
      server({ type: "assistant.tool_finished", tool: "create_event", ok: false }),
    ]);
    assert.equal(s.items[0]!.tools[0]!.state, "failed");
  });

  it("keeps the streamed text if the final text is empty", () => {
    const s = play([
      server({ type: "assistant.text_delta", text: "Done." }),
      server({ type: "assistant.done", status: "done", text: "", pending: [] }),
    ]);
    assert.equal(s.items[0]!.text, "Done.");
  });

  it("shows confirmation cards from the final message, and a decision marks one as sending", () => {
    const pending = [{ action_id: "a1", tool: "delete_event", summary: "Delete the event “Dentist”" }];
    let s = play([server({ type: "assistant.done", status: "needs_confirmation", text: "", pending })]);
    assert.equal(s.busy, false);
    assert.deepEqual(s.pending, [{ ...pending[0]!, sending: false }]);
    s = play([{ kind: "decision_sent", actionId: "a1" }], s);
    assert.equal(s.pending[0]!.sending, true);
    assert.equal(s.busy, true);
    s = play([server({ type: "assistant.done", status: "done", text: "Deleted.", pending: [] })], s);
    assert.deepEqual(s.pending, []);
  });

  it("an error stops the spinner and stops streaming", () => {
    const s = play([
      { kind: "user_sent", text: "hi" },
      server({ type: "assistant.text_delta", text: "partial" }),
      server({ type: "assistant.error", code: "model_unavailable", message: "Try again in a minute." }),
    ]);
    assert.equal(s.busy, false);
    assert.equal(s.error, "Try again in a minute.");
    assert.equal(s.items[1]!.streaming, false);
  });

  it("a new message clears the old error; reset clears everything", () => {
    const s = play([server({ type: "assistant.error", code: "x", message: "boom" }), { kind: "user_sent", text: "again" }]);
    assert.equal(s.error, null);
    assert.deepEqual(play([{ kind: "reset" }], s), initialChatState);
  });

  it("does not mutate earlier states", () => {
    const first = play([{ kind: "user_sent", text: "hi" }]);
    const snapshot = JSON.stringify(first);
    play([server({ type: "assistant.text_delta", text: "x" })], first);
    assert.equal(JSON.stringify(first), snapshot);
  });

  it("ids are unique", () => {
    const s = play([
      { kind: "user_sent", text: "a" },
      server({ type: "assistant.text_delta", text: "b" }),
      server({ type: "assistant.done", status: "done", text: "b", pending: [] }),
      { kind: "user_sent", text: "c" },
    ]);
    assert.equal(new Set(s.items.map((i) => i.id)).size, s.items.length);
  });
});

describe("describeTool", () => {
  it("never shows a raw tool name", () => {
    assert.equal(describeTool("list_events"), "Checking your calendar");
    assert.equal(describeTool("drop_database"), "Working");
  });
});
