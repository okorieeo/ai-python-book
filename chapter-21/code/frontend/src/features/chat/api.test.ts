import { describe, expect, it } from "vitest";
import { toChatMessage } from "./api";

describe("toChatMessage", () => {
  it("maps a stored user message, keeping the client id for de-duplication", () => {
    expect(toChatMessage({ id: "m1", client_id: "k1", role: "user", content: "Hi", created_at: "t" }))
      .toEqual({ id: "m1", clientId: "k1", role: "user", content: "Hi", createdAt: "t", status: "sent" });
  });
  it("maps an assistant message without send status", () => {
    const m = toChatMessage({ id: "a1", client_id: null, role: "assistant", content: "Yo", created_at: "t" });
    expect(m.status).toBeUndefined();
    expect(m.clientId).toBeUndefined();
  });
});
