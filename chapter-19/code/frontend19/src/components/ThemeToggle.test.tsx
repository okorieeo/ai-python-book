import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { ThemeProvider } from "./theme-provider";
import { ThemeToggle } from "./ThemeToggle";

function renderToggle() {
  return render(
    <ThemeProvider attribute="class" defaultTheme="light" enableSystem>
      <ThemeToggle />
    </ThemeProvider>,
  );
}

describe("ThemeToggle", () => {
  it("has an accessible name, though it shows only an icon", () => {
    renderToggle();
    expect(
      screen.getByRole("button", { name: "Choose theme" }),
    ).toBeInTheDocument();
  });

  it("offers Light, Dark and System, with the current one selected", async () => {
    const user = userEvent.setup();
    renderToggle();
    await user.click(screen.getByRole("button", { name: "Choose theme" }));
    expect(screen.getByRole("menuitemradio", { name: "Light" })).toBeChecked();
    expect(
      screen.getByRole("menuitemradio", { name: "Dark" }),
    ).not.toBeChecked();
    expect(
      screen.getByRole("menuitemradio", { name: "System" }),
    ).toBeInTheDocument();
  });

  it("switches the page to dark mode and remembers the choice", async () => {
    const user = userEvent.setup();
    renderToggle();
    await user.click(screen.getByRole("button", { name: "Choose theme" }));
    await user.click(screen.getByRole("menuitemradio", { name: "Dark" }));
    expect(document.documentElement).toHaveClass("dark");
    expect(window.localStorage.getItem("theme")).toBe("dark");
  });

  it("can be used with the keyboard alone", async () => {
    const user = userEvent.setup();
    renderToggle();
    await user.tab(); // focus the button
    await user.keyboard("{Enter}"); // open the menu
    await user.keyboard("{ArrowDown}{Enter}"); // Light is focused; move to Dark and choose it
    expect(document.documentElement).toHaveClass("dark");
  });
});
