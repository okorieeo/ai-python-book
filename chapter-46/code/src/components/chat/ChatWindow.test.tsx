import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { expectNoA11yViolations } from "@/test-utils";
import type { SocketLike } from "@/lib/chat/useChatStream";
import { ChatWindow } from "./ChatWindow";
import { ConversationList } from "./ConversationList";

class FakeSocket implements SocketLike {
  readyState = 0;
  sent: string[] = [];
  onopen: SocketLike["onopen"] = null;
  onmessage: SocketLike["onmessage"] = null;
  onclose: SocketLike["onclose"] = null;
  send(data: string) {
    this.sent.push(data);
  }
  close() {}
  receive(frame: object) {
    this.onmessage?.({ data: JSON.stringify(frame) });
  }
}

async function renderChat() {
  const sockets: FakeSocket[] = [];
  const result = render(
    <ChatWindow
      resolveUrl={async () => "ws://test"}
      socketFactory={() => {
        const s = new FakeSocket();
        sockets.push(s);
        return s;
      }}
    />,
  );
  await screen.findByText("Connecting…");
  const socket = sockets[0]!;
  act(() => {
    socket.readyState = 1;
    socket.onopen?.({});
  });
  return { ...result, socket };
}

describe("ChatWindow", () => {
  it("streams a reply into the log and re-enables the composer when done", async () => {
    const { socket } = await renderChat();
    const user = userEvent.setup();

    await user.type(screen.getByLabelText("Message"), "Hello{Enter}");
    expect(JSON.parse(socket.sent[0]!)).toEqual({ type: "user_message", content: "Hello" });
    expect(screen.getByLabelText("Message")).toBeDisabled();
    expect(screen.getByRole("log")).toHaveAttribute("aria-busy", "true");

    act(() => socket.receive({ type: "token", delta: "Hi **there**" }));
    expect(await screen.findByText("there")).toBeInTheDocument(); // rendered as <strong>
    act(() => socket.receive({ type: "done", message_id: "m1" }));

    expect(screen.getByRole("log")).toHaveAttribute("aria-busy", "false");
    expect(screen.getByLabelText("Message")).toBeEnabled();
  });

  it("renders model output as text, never as HTML or a javascript: link", async () => {
    const { socket, container } = await renderChat();
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Message"), "x{Enter}");
    act(() =>
      socket.receive({
        type: "token",
        delta: '<img src=x onerror="window.pwned=1"> <script>window.pwned=1</script> [click](javascript:window.pwned=1)',
      }),
    );
    await screen.findByText("click");
    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector("img")).toBeNull();
    const link = screen.getByText("click").closest("a");
    expect(link?.getAttribute("href") ?? "").not.toMatch(/^javascript:/i);
    expect((window as unknown as { pwned?: number }).pwned).toBeUndefined();
  });

  it("shows a friendly message for a budget error, not the server text", async () => {
    const { socket } = await renderChat();
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Message"), "x{Enter}");
    act(() => socket.receive({ type: "error", code: "budget_exceeded", message: "internal: tokens 50001>50000" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("today's AI usage limit");
    expect(alert).not.toHaveTextContent("internal");
  });

  it("Shift+Enter adds a line instead of sending", async () => {
    const { socket } = await renderChat();
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Message"), "a{Shift>}{Enter}{/Shift}b");
    expect(socket.sent).toHaveLength(0);
    expect(screen.getByLabelText("Message")).toHaveValue("a\nb");
  });

  it("has no automatically detectable accessibility violations while streaming", async () => {
    const { socket, container } = await renderChat();
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Message"), "x{Enter}");
    act(() => socket.receive({ type: "token", delta: "```py\nprint(1)\n```\n\nSome *text*." }));
    await screen.findByText("print(1)");
    await expectNoA11yViolations(container);
  });
});

describe("ConversationList", () => {
  const items = [
    { public_id: "a1", title: "Trip plan", updated_at: "2026-11-01T10:00:00Z" },
    { public_id: "b2", title: "", updated_at: "2026-11-02T10:00:00Z" },
  ];

  it("marks the current conversation and labels the navigation", async () => {
    const { container } = render(<ConversationList conversations={items} activeId="a1" />);
    await act(async () => {});
    expect(screen.getByRole("navigation", { name: "Conversations" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Trip plan" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Untitled" })).not.toHaveAttribute("aria-current");
    await expectNoA11yViolations(container);
  });

  it("explains an empty list", () => {
    render(<ConversationList conversations={[]} />);
    expect(screen.getByText(/no conversations yet/i)).toBeInTheDocument();
  });
});
