// @vitest-environment node
import { describe, expect, it } from "vitest";
import { parseServerEvent } from "./protocol";
import { chatReducer, initialChatState, type ChatState } from "./reducer";

const sent = (state = initialChatState) => chatReducer(state, { type: "user_sent", id: "u1", content: "Hi" });
const token = (state: ChatState, delta: string) => chatReducer(state, { type: "server_event", event: { type: "token", delta } });

describe("chatReducer", () => {
  it("adds the user message and an empty pending reply", () => {
    const state = sent();
    expect(state.status).toBe("streaming");
    expect(state.messages.map((m) => [m.role, m.content, m.pending])).toEqual([
      ["user", "Hi", undefined],
      ["assistant", "", true],
    ]);
  });

  it("appends tokens to the pending reply in order", () => {
    let state = sent();
    for (const part of ["Hel", "lo", " there"]) state = token(state, part);
    expect(state.messages.at(-1)?.content).toBe("Hello there");
  });

  it("finishes on done: real id, no longer pending, ready for the next message", () => {
    let state = token(sent(), "Hello");
    state = chatReducer(state, { type: "server_event", event: { type: "done", message_id: "m42" } });
    expect(state.status).toBe("idle");
    expect(state.messages.at(-1)).toMatchObject({ id: "m42", content: "Hello", pending: false });
  });

  it("ignores a stray token that arrives after done", () => {
    let state = token(sent(), "Hello");
    state = chatReducer(state, { type: "server_event", event: { type: "done", message_id: "m1" } });
    const after = token(state, " late");
    expect(after).toBe(state); // same object: nothing changed
  });

  it("keeps the partial text when the server reports an error", () => {
    let state = token(sent(), "Partial");
    state = chatReducer(state, { type: "server_event", event: { type: "error", code: "budget_exceeded", message: "x" } });
    expect(state.status).toBe("error");
    expect(state.error?.code).toBe("budget_exceeded");
    expect(state.messages.at(-1)).toMatchObject({ content: "Partial", pending: false });
  });

  it("marks the reply finished when the connection drops mid-stream", () => {
    const state = chatReducer(token(sent(), "Half"), { type: "connection_lost" });
    expect(state.error?.code).toBe("connection_lost");
    expect(state.messages.at(-1)?.pending).toBe(false);
  });

  it("does not invent an error when an idle connection drops", () => {
    const idle = chatReducer(initialChatState, { type: "connection_lost" });
    expect(idle).toBe(initialChatState);
  });

  it("does not mutate the previous state", () => {
    const before = sent();
    const snapshot = JSON.stringify(before);
    token(before, "x");
    expect(JSON.stringify(before)).toBe(snapshot);
  });
});

describe("parseServerEvent", () => {
  it("accepts the three known frames", () => {
    expect(parseServerEvent('{"type":"token","delta":"a"}')).toEqual({ type: "token", delta: "a" });
    expect(parseServerEvent('{"type":"done","message_id":"1"}')).toEqual({ type: "done", message_id: "1" });
    expect(parseServerEvent('{"type":"error","code":"c","message":"m"}')).toMatchObject({ type: "error" });
  });

  it.each([
    ["not json", "{nope"],
    ["unknown type", '{"type":"hack","delta":"a"}'],
    ["wrong field type", '{"type":"token","delta":5}'],
    ["binary frame", new ArrayBuffer(4)],
  ])("drops %s", (_name, raw) => {
    expect(parseServerEvent(raw)).toBeNull();
  });
});
