import { render } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { accessibilityProblems } from "../../test/axe";
import { plans } from "@/lib/plans";
import { ChatPanel } from "./ChatPanel";
import { MessageList } from "./MessageList";
import { MobileNav } from "./MobileNav";
import { PricingTable } from "./PricingTable";
import { ThemeProvider } from "./theme-provider";
import { ThemeToggle } from "./ThemeToggle";

const messages = [
  {
    id: 1,
    role: "user" as const,
    content: "Hello",
    createdAt: "2026-11-02T09:00:00Z",
  },
  {
    id: 2,
    role: "assistant" as const,
    content: "Hi there",
    createdAt: "2026-11-02T09:00:01Z",
  },
];

describe("accessibility checks (axe)", () => {
  it("pricing table", async () => {
    const { container } = render(<PricingTable plans={plans} />);
    expect(await accessibilityProblems(container)).toEqual([]);
  });

  it("message list and chat panel", async () => {
    const list = render(<MessageList messages={messages} />);
    expect(await accessibilityProblems(list.container)).toEqual([]);
    const panel = render(
      <ChatPanel conversationId="c" initialMessages={messages} />,
    );
    expect(await accessibilityProblems(panel.container)).toEqual([]);
  });

  it("theme menu, closed and open", async () => {
    const { container } = render(
      <ThemeProvider attribute="class">
        <ThemeToggle />
      </ThemeProvider>,
    );
    expect(await accessibilityProblems(container)).toEqual([]);
    await userEvent.click(container.querySelector("button")!);
    expect(await accessibilityProblems(document.body)).toEqual([]);
  });

  it("mobile navigation panel", async () => {
    const { baseElement } = render(
      <MobileNav>
        <a href="#one">One</a>
      </MobileNav>,
    );
    await userEvent.click(baseElement.querySelector("button")!);
    expect(await accessibilityProblems(document.body)).toEqual([]);
  });

  it("the checker really does catch mistakes", async () => {
    const { container } = render(
      <div>
        <input type="text" />
        {/* eslint-disable-next-line @next/next/no-img-element, jsx-a11y/alt-text -- the missing alt is the point of this test */}
        <img src="/x.png" />
        <button></button>
      </div>,
    );
    const problems = (await accessibilityProblems(container)).join("\n");
    expect(problems).toContain("label"); // input without a label
    expect(problems).toContain("image-alt"); // image without alt text
    expect(problems).toContain("button-name"); // button with no name
  });
});
