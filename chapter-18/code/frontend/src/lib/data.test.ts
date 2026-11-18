// @vitest-environment node
import { describe, expect, it } from "vitest";
import {
  addMessage,
  createConversation,
  getConversation,
  listConversations,
} from "./data";

describe("the mock data layer", () => {
  it("starts with seeded conversations", async () => {
    const list = await listConversations();
    expect(list.map((c) => c.id)).toEqual(
      expect.arrayContaining(["welcome", "invoices"]),
    );
  });

  it("creates a conversation with a default title", async () => {
    const created = await createConversation("   ");
    expect(created.title).toBe("New conversation");
    expect((await getConversation(created.id))?.messages).toEqual([]);
  });

  it("adds the user's message and an answer, with increasing ids", async () => {
    const { id } = await createConversation();
    const result = await addMessage(id, "Hello");
    expect(result?.userMessage).toMatchObject({
      role: "user",
      content: "Hello",
    });
    expect(result?.assistantMessage).toMatchObject({
      role: "assistant",
      content: "Echo: Hello",
    });
    expect(result!.assistantMessage.id).toBeGreaterThan(result!.userMessage.id);
    expect((await getConversation(id))?.messages).toHaveLength(2);
  });

  it("returns null for unknown conversations", async () => {
    expect(await getConversation("nope")).toBeNull();
    expect(await addMessage("nope", "Hi")).toBeNull();
  });
});
