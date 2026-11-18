import { describe, expect, it } from "vitest";
import { encodeCommand, parseServerEvent } from "./protocol";

describe("parseServerEvent", () => {
  it("parses every event type the backend sends", () => {
    const samples = [
      { type: "message.accepted", conversation_id: "c1", client_id: "k1",
        message: { id: "m1", role: "user", content: "hi", created_at: "2026-11-03T10:00:00Z" } },
      { type: "assistant.start", conversation_id: "c1", message_id: "m2" },
      { type: "assistant.delta", message_id: "m2", delta: "Hel" },
      { type: "assistant.end", message_id: "m2", finish_reason: "stop",
        usage: { input_tokens: 12, output_tokens: 34 } },
      { type: "error", code: "rate_limited", message: "Slow down", retry_after: 50 },
      { type: "pong" },
    ];
    for (const sample of samples) {
      const parsed = parseServerEvent(JSON.stringify(sample));
      expect(parsed?.type).toBe(sample.type);
    }
  });

  it("accepts an empty delta (providers sometimes send one)", () => {
    const parsed = parseServerEvent('{"type":"assistant.delta","message_id":"m","delta":""}');
    expect(parsed).toEqual({ type: "assistant.delta", message_id: "m", delta: "" });
  });

  it("returns null for anything it does not understand", () => {
    const bad = [
      "not json",
      "[]",
      "null",
      '{"type":"unknown.event"}',
      '{"type":"assistant.delta","message_id":"m"}',            // delta missing
      '{"type":"assistant.delta","message_id":"","delta":"x"}', // empty id
      '{"type":"assistant.end","message_id":"m","finish_reason":"banana"}',
    ];
    for (const raw of bad) expect(parseServerEvent(raw)).toBeNull();
    expect(parseServerEvent(new ArrayBuffer(8))).toBeNull();
    expect(parseServerEvent(undefined)).toBeNull();
  });

  it("drops unknown extra fields instead of trusting them", () => {
    const parsed = parseServerEvent('{"type":"pong","is_admin":true}');
    expect(parsed).toEqual({ type: "pong" });
  });
});

describe("encodeCommand", () => {
  it("produces JSON the backend can read", () => {
    const text = encodeCommand({
      type: "message.send", conversation_id: "c1", client_id: "k1", content: "hi",
    });
    expect(JSON.parse(text)).toEqual({
      type: "message.send", conversation_id: "c1", client_id: "k1", content: "hi",
    });
  });
});
