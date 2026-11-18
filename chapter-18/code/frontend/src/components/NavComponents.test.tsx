import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

const push = vi.fn();
const refresh = vi.fn();
const pathname = "/chat/welcome";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, refresh }),
  usePathname: () => pathname,
}));

import { ConversationLink } from "./ConversationLink";
import { NewChatButton } from "./NewChatButton";

afterEach(() => {
  vi.unstubAllGlobals();
  push.mockClear();
  refresh.mockClear();
});

describe("ConversationLink", () => {
  it("marks the link of the open conversation as current", () => {
    render(
      <>
        <ConversationLink id="welcome" title="Welcome" />
        <ConversationLink id="invoices" title="Invoices" />
      </>,
    );
    expect(screen.getByRole("link", { name: "Welcome" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(screen.getByRole("link", { name: "Invoices" })).not.toHaveAttribute(
      "aria-current",
    );
    expect(screen.getByRole("link", { name: "Invoices" })).toHaveAttribute(
      "href",
      "/chat/invoices",
    );
  });
});

describe("NewChatButton", () => {
  it("creates a conversation, opens it and refreshes the sidebar", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => Response.json({ id: "abc" }, { status: 201 })),
    );
    const user = userEvent.setup();
    render(<NewChatButton />);
    await user.click(screen.getByRole("button", { name: "New chat" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/chat/abc"));
    expect(refresh).toHaveBeenCalled();
  });

  it("shows an error and does not navigate when creation fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(null, { status: 500 })),
    );
    const user = userEvent.setup();
    render(<NewChatButton />);
    await user.click(screen.getByRole("button", { name: "New chat" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
  });
});
