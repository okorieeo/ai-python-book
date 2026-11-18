import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Button } from "./button";

describe("Button", () => {
  it("is a real button that can be clicked", async () => {
    const onClick = vi.fn();
    render(<Button onClick={onClick}>Save</Button>);
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("applies a variant and a size", () => {
    render(
      <Button variant="destructive" size="sm">
        Delete
      </Button>,
    );
    const button = screen.getByRole("button", { name: "Delete" });
    expect(button).toHaveClass("bg-destructive", "h-9");
    expect(button).not.toHaveClass("bg-primary");
  });

  it("lets the caller override a style with className", () => {
    render(<Button className="h-14">Big</Button>);
    const button = screen.getByRole("button", { name: "Big" });
    expect(button).toHaveClass("h-14");
    expect(button).not.toHaveClass("h-10"); // the default was replaced, not stacked
  });

  it("cannot be clicked when disabled", async () => {
    const onClick = vi.fn();
    render(
      <Button disabled onClick={onClick}>
        Save
      </Button>,
    );
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(onClick).not.toHaveBeenCalled();
  });

  it("with asChild, gives a link the look of a button", () => {
    render(
      <Button asChild>
        <a href="#chat">Open app</a>
      </Button>,
    );
    const link = screen.getByRole("link", { name: "Open app" });
    expect(link).toHaveAttribute("href", "#chat");
    expect(link).toHaveClass("bg-primary");
    expect(screen.queryByRole("button")).toBeNull(); // no nested button
  });
});
