import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Message } from "@/lib/types";
import { ChatPanel } from "./ChatPanel";

const history: Message[] = [
  {
    id: 1,
    role: "user",
    content: "Earlier question",
    createdAt: "2026-11-01T09:00:00Z",
  },
];

const reply = {
  userMessage: {
    id: 10,
    role: "user",
    content: "Hello",
    createdAt: "2026-11-02T09:00:00Z",
  },
  assistantMessage: {
    id: 11,
    role: "assistant",
    content: "Echo: Hello",
    createdAt: "2026-11-02T09:00:01Z",
  },
};

function mockFetch(impl: () => Promise<Response>) {
  const fn = vi.fn(impl);
  vi.stubGlobal("fetch", fn);
  return fn;
}

afterEach(() => vi.unstubAllGlobals());

describe("ChatPanel", () => {
  it("shows the existing messages", () => {
    render(<ChatPanel conversationId="c1" initialMessages={history} />);
    expect(screen.getByText("Earlier question")).toBeInTheDocument();
  });

  it("keeps the Send button disabled until there is text", async () => {
    const user = userEvent.setup();
    render(<ChatPanel conversationId="c1" initialMessages={[]} />);
    const send = screen.getByRole("button", { name: "Send" });
    expect(send).toBeDisabled();
    await user.type(screen.getByLabelText("Message"), "   ");
    expect(send).toBeDisabled(); // spaces only do not count
    await user.type(screen.getByLabelText("Message"), "Hi");
    expect(send).toBeEnabled();
  });

  it("shows the message at once, then replaces it with the server's answer", async () => {
    let finish!: (r: Response) => void;
    const fetchMock = mockFetch(
      () => new Promise((resolve) => (finish = resolve)),
    );
    const user = userEvent.setup();
    render(<ChatPanel conversationId="c1" initialMessages={[]} />);

    await user.type(screen.getByLabelText("Message"), "Hello");
    await user.click(screen.getByRole("button", { name: "Send" }));

    // Optimistic: visible before the server has answered.
    expect(screen.getByText("Hello")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(/typing/i);
    expect(screen.getByLabelText("Message")).toHaveValue(""); // the box was cleared

    finish(Response.json(reply, { status: 201 }));
    expect(await screen.findByText("Echo: Hello")).toBeInTheDocument();
    expect(screen.queryByRole("status")).toBeNull();
    expect(screen.getAllByText("Hello")).toHaveLength(1); // not duplicated

    const [url, init] = fetchMock.mock.calls[0] as unknown as [
      string,
      RequestInit,
    ];
    expect(url).toBe("/api/conversations/c1/messages");
    expect(JSON.parse(init.body as string)).toEqual({ content: "Hello" });
  });

  it("sends on Enter, and adds a new line on Shift+Enter", async () => {
    const fetchMock = mockFetch(async () =>
      Response.json(reply, { status: 201 }),
    );
    const user = userEvent.setup();
    render(<ChatPanel conversationId="c1" initialMessages={[]} />);
    const box = screen.getByLabelText("Message");

    await user.type(box, "line one{Shift>}{Enter}{/Shift}line two");
    expect(box).toHaveValue("line one\nline two");
    expect(fetchMock).not.toHaveBeenCalled();

    await user.type(box, "{Enter}");
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
  });

  it("undoes the optimistic message and restores the text when sending fails", async () => {
    mockFetch(async () => Response.json({ error: {} }, { status: 500 }));
    const user = userEvent.setup();
    render(<ChatPanel conversationId="c1" initialMessages={[]} />);

    await user.type(screen.getByLabelText("Message"), "Important text");
    await user.click(screen.getByRole("button", { name: "Send" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/not sent/i);
    expect(screen.getByLabelText("Message")).toHaveValue("Important text");
    expect(screen.queryByRole("list", { name: "Messages" })).toBeNull();
  });

  it("remembers an unsent draft between visits", async () => {
    const user = userEvent.setup();
    const first = render(
      <ChatPanel conversationId="c1" initialMessages={[]} />,
    );
    await user.type(screen.getByLabelText("Message"), "half-written");
    first.unmount();

    render(<ChatPanel conversationId="c1" initialMessages={[]} />);
    expect(screen.getByLabelText("Message")).toHaveValue("half-written");

    render(<ChatPanel conversationId="other" initialMessages={[]} />);
    expect(screen.getAllByLabelText("Message")[1]).toHaveValue(""); // drafts are per conversation
  });
});
