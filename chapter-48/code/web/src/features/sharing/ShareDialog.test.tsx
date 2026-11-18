import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi, describe, it, expect, beforeEach } from "vitest";
import { ShareDialog } from "./ShareDialog";
import * as sharing from "@/lib/api/sharing";

vi.mock("@/lib/api/sharing");

const active = { id: "l1", state: "active", created_at: "2026-11-08T10:00:00Z", expires_at: null, view_count: 2 } as const;

describe("ShareDialog", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(sharing.listShareLinks).mockResolvedValue([]);
  });

  it("AC-1: creates a link with the chosen lifetime", async () => {
    vi.mocked(sharing.createShareLink).mockResolvedValue({ ...active, url: "https://app.example.com/s/abc" });
    render(<ShareDialog conversationId="c1" onClose={() => {}} />);
    await userEvent.selectOptions(screen.getByLabelText("Link works for"), "30d");
    await userEvent.click(screen.getByRole("button", { name: "Create link" }));
    await waitFor(() => expect(sharing.createShareLink).toHaveBeenCalledWith("c1", "30d"));
  });

  it("AC-11: shows the link with a copy button", async () => {
    vi.mocked(sharing.createShareLink).mockResolvedValue({ ...active, url: "https://app.example.com/s/abc" });
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    render(<ShareDialog conversationId="c1" onClose={() => {}} />);
    await userEvent.click(screen.getByRole("button", { name: "Create link" }));
    expect(await screen.findByLabelText("Share link")).toHaveValue("https://app.example.com/s/abc");
    await userEvent.click(screen.getByRole("button", { name: "Copy link" }));
    expect(writeText).toHaveBeenCalledWith("https://app.example.com/s/abc");
  });

  it("AC-2 and AC-13: the list shows state and views but never a link", async () => {
    vi.mocked(sharing.listShareLinks).mockResolvedValue([active]);
    render(<ShareDialog conversationId="c1" onClose={() => {}} />);
    expect(await screen.findByText(/active · 2 views/)).toBeInTheDocument();
    expect(screen.queryByLabelText("Share link")).not.toBeInTheDocument();
  });

  it("AC-5: revoking calls the API and refreshes the list", async () => {
    vi.mocked(sharing.listShareLinks).mockResolvedValueOnce([active]).mockResolvedValue([{ ...active, state: "revoked" }]);
    vi.mocked(sharing.revokeShareLink).mockResolvedValue();
    render(<ShareDialog conversationId="c1" onClose={() => {}} />);
    await userEvent.click(await screen.findByRole("button", { name: "Revoke" }));
    await waitFor(() => expect(sharing.revokeShareLink).toHaveBeenCalledWith("c1", "l1"));
    expect(await screen.findByText(/revoked/)).toBeInTheDocument();
  });
});
