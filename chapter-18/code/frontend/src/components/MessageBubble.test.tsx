import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MessageBubble } from "./MessageBubble";

describe("MessageBubble", () => {
  it("shows the message text", () => {
    render(
      <MessageBubble message={{ role: "assistant", content: "Hello!" }} />,
    );
    expect(screen.getByText("Hello!")).toBeInTheDocument();
  });

  it("styles user and assistant messages differently", () => {
    const { rerender } = render(
      <MessageBubble message={{ role: "user", content: "Hi" }} />,
    );
    expect(screen.getByText("Hi")).toHaveAttribute("data-role", "user");
    rerender(<MessageBubble message={{ role: "assistant", content: "Hi" }} />);
    expect(screen.getByText("Hi")).toHaveAttribute("data-role", "assistant");
  });

  it("never turns message text into HTML", () => {
    render(
      <MessageBubble
        message={{ role: "user", content: "<img src=x onerror=alert(1)>" }}
      />,
    );
    expect(
      screen.getByText("<img src=x onerror=alert(1)>"),
    ).toBeInTheDocument();
    expect(document.querySelector("img")).toBeNull(); // React escaped it
  });
});
