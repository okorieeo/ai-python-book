import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import ConversationPage from "./page";

// A Server Component is an async function: call it, await it, render what it returns.
const open = (id: string) =>
  ConversationPage({ params: Promise.resolve({ id }) } as never);

describe("the conversation page", () => {
  it("loads the conversation on the server and hands its messages to the chat", async () => {
    render(await open("welcome"));
    expect(screen.getByText("What can you help me with?")).toBeInTheDocument();
    expect(screen.getByLabelText("Message")).toBeInTheDocument();
  });

  it("renders the not-found page for an unknown id", async () => {
    await expect(open("does-not-exist")).rejects.toMatchObject({
      digest: expect.stringContaining("404"),
    });
  });
});
