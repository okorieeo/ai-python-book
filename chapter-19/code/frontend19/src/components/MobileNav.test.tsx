import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { MobileNav } from "./MobileNav";

const renderNav = () =>
  render(
    <MobileNav>
      <a href="#welcome">Welcome</a>
      <button>New chat</button>
    </MobileNav>,
  );

describe("MobileNav", () => {
  it("starts closed", () => {
    renderNav();
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("opens a labelled dialog from the menu button", async () => {
    const user = userEvent.setup();
    renderNav();
    await user.click(
      screen.getByRole("button", { name: "Open conversations" }),
    );
    const dialog = screen.getByRole("dialog", { name: "Conversations" });
    expect(dialog).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Welcome" })).toBeInTheDocument();
  });

  it("closes with the Escape key and returns focus to the menu button", async () => {
    const user = userEvent.setup();
    renderNav();
    const menuButton = screen.getByRole("button", {
      name: "Open conversations",
    });
    await user.click(menuButton);
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(menuButton).toHaveFocus();
  });

  it("closes when a link inside is followed, but not for other clicks", async () => {
    const user = userEvent.setup();
    renderNav();
    await user.click(
      screen.getByRole("button", { name: "Open conversations" }),
    );
    await user.click(screen.getByRole("button", { name: "New chat" }));
    expect(screen.getByRole("dialog")).toBeInTheDocument(); // still open
    await user.click(screen.getByRole("link", { name: "Welcome" }));
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("closes with the Close button", async () => {
    const user = userEvent.setup();
    renderNav();
    await user.click(
      screen.getByRole("button", { name: "Open conversations" }),
    );
    await user.click(screen.getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
