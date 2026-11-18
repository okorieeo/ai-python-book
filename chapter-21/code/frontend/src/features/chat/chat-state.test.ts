import { describe, expect, it } from "vitest";
import type { ServerEvent } from "@/lib/realtime/protocol";
import {
  chatReducer, findStaleSending, initialChatState, mergeForDisplay,
  type ChatAction, type ChatMessage, type ChatState,
} from "./chat-state";

const C = "conv-1";
const run = (state: ChatState, ...actions: ChatAction[]) => actions.reduce(chatReducer, state);
const server = (event: ServerEvent): ChatAction => ({ type: "server", event });
const send = (clientId = "k1", now = 1000): ChatAction =>
  ({ type: "local/send", conversationId: C, clientId, content: "Hello", now });
const accepted = (clientId = "k1", id = "m1"): ChatAction => server({
  type: "message.accepted", conversation_id: C, client_id: clientId,
  message: { id, role: "user", content: "Hello", created_at: "2026-11-03T10:00:00.000Z" },
});
const start = (id = "a1"): ChatAction => server({ type: "assistant.start", conversation_id: C, message_id: id });
const delta = (text: string, id = "a1"): ChatAction => server({ type: "assistant.delta", message_id: id, delta: text });
const end = (reason: "stop" | "length" | "stopped" | "error" = "stop", id = "a1"): ChatAction =>
  server({ type: "assistant.end", message_id: id, finish_reason: reason });
const msgs = (s: ChatState) => s[C]?.messages ?? [];

describe("a normal turn", () => {
  it("shows the user message at once, as sending", () => {
    const s = run(initialChatState, send());
    expect(msgs(s)).toHaveLength(1);
    expect(msgs(s)[0]).toEqual({
      id: "k1", clientId: "k1", role: "user", content: "Hello",
      createdAt: "1970-01-01T00:00:01.000Z", status: "sending", sentAt: 1000, attachmentIds: undefined,
    });
    expect(s[C]?.awaitingReply).toBe(true);
  });

  it("swaps in the server id when the message is accepted", () => {
    const s = run(initialChatState, send(), accepted());
    expect(msgs(s)).toHaveLength(1);
    expect(msgs(s)[0]?.id).toBe("m1");
    expect(msgs(s)[0]?.clientId).toBe("k1");
    expect(msgs(s)[0]?.status).toBe("sent");
  });

  it("streams an answer: start, deltas, end", () => {
    const s = run(initialChatState, send(), accepted(), start(), delta("Hel"), delta("lo!"));
    const reply = msgs(s)[1]!;
    expect(reply.content).toBe("Hello!");
    expect(reply.streaming).toBe(true);
    expect(s[C]?.generatingId).toBe("a1");
    expect(s[C]?.awaitingReply).toBe(false);
    const done = run(s, end("stop"));
    expect(msgs(done)[1]?.streaming).toBe(false);
    expect(msgs(done)[1]?.finishReason).toBe("stop");
    expect(done[C]?.generatingId).toBeNull();
  });

  it("records why a reply stopped early", () => {
    const s = run(initialChatState, start(), delta("abc"), end("length"));
    expect(msgs(s)[0]?.finishReason).toBe("length");
  });
});

describe("robustness", () => {
  it("ignores a duplicate acknowledgement and a duplicate start", () => {
    const once = run(initialChatState, send(), accepted(), start());
    const twice = run(once, accepted(), start());
    expect(twice).toBe(once); // exactly the same object: nothing changed
  });

  it("ignores deltas for messages it has never seen, and empty deltas", () => {
    expect(run(initialChatState, delta("x", "ghost"))).toBe(initialChatState);
    const s = run(initialChatState, start());
    expect(run(s, delta(""))).toBe(s);
  });

  it("ignores a late delta after the message ended", () => {
    const s = run(initialChatState, start(), delta("a"), end());
    expect(run(s, delta("late"))).toBe(s);
  });

  it("adds an accepted message it did not know about (another tab)", () => {
    const s = run(initialChatState, accepted("other", "m9"));
    expect(msgs(s)[0]?.id).toBe("m9");
  });

  it("leaves other conversations untouched (same object reference)", () => {
    const other = run(initialChatState,
      { type: "local/send", conversationId: "conv-2", clientId: "k2", content: "Hi", now: 1 });
    const s = run(other, send());
    expect(s["conv-2"]).toBe(other["conv-2"]);
  });
});

describe("failures", () => {
  it("fails a send and lets the user retry the same message", () => {
    let s = run(initialChatState, send(), { type: "local/fail", conversationId: C, clientId: "k1", reason: "offline" });
    expect(msgs(s)[0]?.status).toBe("failed");
    expect(msgs(s)[0]?.error).toBe("offline");
    expect(s[C]?.awaitingReply).toBe(false);
    s = run(s, { type: "local/resend", conversationId: C, clientId: "k1", now: 5000 });
    expect(msgs(s)).toHaveLength(1);            // same message, not a second one
    expect(msgs(s)[0]?.status).toBe("sending");
    expect(msgs(s)[0]?.error).toBeUndefined();
    expect(msgs(s)[0]?.sentAt).toBe(5000);
  });

  it("does not fail a message that was already accepted", () => {
    const s = run(initialChatState, send(), accepted(),
      { type: "local/fail", conversationId: C, clientId: "k1", reason: "late timeout" });
    expect(msgs(s)[0]?.status).toBe("sent");
  });

  it("a rate-limit error fails only that send and keeps the retry-after", () => {
    const s = run(initialChatState, send(), server({
      type: "error", code: "rate_limited", message: "Slow down", client_id: "k1", retry_after: 50,
    }));
    expect(msgs(s)[0]?.status).toBe("failed");
    expect(s[C]?.error).toEqual({ code: "rate_limited", message: "Slow down", retryAfter: 50 });
    expect(run(s, { type: "local/dismiss_error", conversationId: C })[C]?.error).toBeNull();
  });

  it("a generation error stops the stream where it was", () => {
    const s = run(initialChatState, start(), delta("part"), server({
      type: "error", code: "provider_error", message: "Model unavailable", conversation_id: C,
    }));
    expect(msgs(s)[0]?.content).toBe("part");
    expect(msgs(s)[0]?.streaming).toBe(false);
    expect(msgs(s)[0]?.finishReason).toBe("error");
    expect(s[C]?.generatingId).toBeNull();
  });

  it("a dropped connection interrupts a stream and fails unsent messages", () => {
    const s = run(initialChatState, send("k1"), accepted("k1", "m1"), start(), delta("half an ans"),
      send("k2", 2000), { type: "connection/lost" });
    expect(msgs(s)[1]?.finishReason).toBe("interrupted");
    expect(msgs(s)[1]?.content).toBe("half an ans"); // the partial text is kept
    expect(msgs(s)[2]?.status).toBe("failed");
    expect(s[C]?.generatingId).toBeNull();
    expect(s[C]?.awaitingReply).toBe(false);
  });

  it("connection/lost changes nothing when nothing was in flight", () => {
    const s = run(initialChatState, send(), accepted(), start(), delta("x"), end());
    expect(run(s, { type: "connection/lost" })).toBe(s);
  });
});

describe("pruning confirmed messages", () => {
  it("removes finished messages the server history now contains", () => {
    const s = run(initialChatState, send(), accepted(), start(), delta("Hi"), end());
    const pruned = run(s, { type: "prune", conversationId: C, confirmedIds: ["m1", "a1"] });
    expect(msgs(pruned)).toHaveLength(0);
  });

  it("never prunes a message that is still streaming or failed", () => {
    const s = run(initialChatState, start(), delta("Hi"), send("k9"),
      { type: "local/fail", conversationId: C, clientId: "k9", reason: "x" });
    const pruned = run(s, { type: "prune", conversationId: C, confirmedIds: ["a1", "k9"] });
    expect(msgs(pruned)).toHaveLength(2);
  });

  it("returns the same state when there is nothing to prune", () => {
    const s = run(initialChatState, send());
    expect(run(s, { type: "prune", conversationId: C, confirmedIds: ["zzz"] })).toBe(s);
  });
});

describe("mergeForDisplay", () => {
  const h = (id: string, extra: Partial<ChatMessage> = {}): ChatMessage =>
    ({ id, role: "user", content: id, createdAt: "", ...extra });

  it("puts local messages after history", () => {
    expect(mergeForDisplay([h("a"), h("b")], [h("c")]).map((m) => m.id)).toEqual(["a", "b", "c"]);
  });
  it("does not show a message twice once history contains it (by id)", () => {
    expect(mergeForDisplay([h("a"), h("b")], [h("b"), h("c")]).map((m) => m.id)).toEqual(["a", "b", "c"]);
  });
  it("matches by client id when the server id was never learned", () => {
    const history = [h("server-7", { clientId: "k7" })];
    const live = [h("k7", { clientId: "k7", status: "sending" })];
    expect(mergeForDisplay(history, live)).toBe(history);
  });
  it("returns the history array itself when there is nothing extra", () => {
    const history = [h("a")];
    expect(mergeForDisplay(history, [])).toBe(history);
  });
});

describe("findStaleSending", () => {
  it("finds messages that were never acknowledged in time", () => {
    const s = run(initialChatState, send("old", 1000), send("new", 9000), send("acked", 1000), accepted("acked", "m5"));
    expect(findStaleSending(s, 12_000, 10_000)).toEqual([{ conversationId: C, clientId: "old" }]);
    expect(findStaleSending(s, 5_000, 10_000)).toEqual([]);
  });
});
