// @vitest-environment node
import { describe, expect, it } from "vitest";
import { createConversation } from "@/lib/data";
import { POST } from "./route";

const call = async (id: string, body: string) => {
  const request = new Request("http://localhost/api/conversations/x/messages", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
  });
  return POST(request, { params: Promise.resolve({ id }) } as never);
};

describe("POST /api/conversations/{id}/messages", () => {
  it("creates the message and the answer", async () => {
    const { id } = await createConversation();
    const response = await call(
      id,
      JSON.stringify({ content: "  Hi there  " }),
    );
    expect(response.status).toBe(201);
    const data = await response.json();
    expect(data.userMessage.content).toBe("Hi there"); // trimmed
    expect(data.assistantMessage.role).toBe("assistant");
  });

  it("rejects blank or oversized content with the standard error format", async () => {
    const { id } = await createConversation();
    for (const content of ["   ", "x".repeat(8001), 42]) {
      const response = await call(id, JSON.stringify({ content }));
      expect(response.status).toBe(422);
      const { error } = await response.json();
      expect(error.code).toBe("validation_error");
      expect(error.details.content).toBeDefined();
      expect(error.request_id).toMatch(/^req_/);
    }
  });

  it("rejects bodies that are not JSON", async () => {
    const { id } = await createConversation();
    const response = await call(id, "not json");
    expect(response.status).toBe(400);
    expect((await response.json()).error.code).toBe("invalid_json");
  });

  it("returns 404 for an unknown conversation", async () => {
    const response = await call("missing", JSON.stringify({ content: "Hi" }));
    expect(response.status).toBe(404);
  });
});
