# Chapter 19 — Styling and Component Libraries: extended material

The printed edition of *Building AI-Powered Apps* keeps each chapter short. This file holds the longer material that was moved here so that nothing is lost: the full hands-on lab, troubleshooting tables, checklists, further exercises, and sections that were condensed for print.


---

# Sections condensed for print


## Tailwind CSS 4 › The utilities you will use every day

| **Area** | **Examples** | **Meaning** |
|---|---|---|
| **Layout** | `flex`  `grid`  `hidden`  `block`  `gap-4`  `items-center`  `justify-between` | How children are arranged |
| **Spacing** | `p-4`  `px-3`  `py-2`  `m-auto`  `mt-2`  `space-y-2` | Padding and margin; each step is 0.25rem, so `p-4` = 1rem |
| **Sizing** | `w-64`  `h-10`  `size-5`  `max-w-5xl`  `min-h-0`  `h-dvh` | `size-5` sets width and height together; `dvh` is the visible screen height on phones |
| **Typography** | `text-sm`  `font-medium`  `tracking-tight`  `text-balance`  `truncate` | Size, weight, spacing, wrapping |
| **Colour** | `bg-primary`  `text-muted-foreground`  `border-border`  `bg-primary/90` | `/90` is 90% opacity |
| **Borders and effects** | `rounded-md`  `border`  `shadow-sm`  `ring-2`  `opacity-60` | Shape, outline, depth |
| **Motion** | `transition-colors`  `animate-pulse`  `motion-reduce:animate-none` | Animation, switched off for people who ask for less motion |


## Tailwind CSS 4 › Two rules that prevent most Tailwind bugs

> **Write complete class names**
>
> Tailwind finds classes by scanning your source files for text that *looks like* a class. It cannot run your code. This works: `color === "red" ? "bg-red-600" : "bg-blue-600"`. This does **not**: `' `bg-${color}-600` . The class `bg-red-600` never appears in the source, so it is never generated, and the element is unstyled in production. Always write out the full class name, or map values to full strings (`const styles = { red: "bg-red-600", blue: "bg-blue-600" }`).

> **Do not fight the cascade with @apply**
>
> Tailwind lets you write `@apply px-4 py-2` inside a CSS rule to bundle utilities into one class. It is tempting, and it brings back the naming and sharing problems utilities solved. Our `globals.css` uses it in two small places (the global border colour and the `body`). For everything else, make a **component** instead. A React component is a better "class" than a CSS class: it can take props, and it keeps markup and style together.


## Design Tokens › Contrast is a number, so measure it

Text that is hard to read is the most common accessibility failure. The **Web Content Accessibility Guidelines (WCAG)** define it as a number, the *contrast ratio* between two colours, from 1:1 (identical) to 21:1 (black on white). Level **AA**, the usual legal and practical target, requires **4.5:1** for normal text and **3:1** for large text and for the outlines of controls such as inputs. The figure below is generated from the real tokens in our CSS:

*(figure: see the printed book)*

Our palette was not eyeballed. A test reads `globals.css`, computes the contrast of every text pair in **both** themes, and fails if any drops below the minimum. Anyone who later "improves" a colour is told immediately if they have made the page harder to read.

**test/contrast.ts**

```
/** WCAG 2 contrast ratio between two #rrggbb colours (1 = identical, 21 = black on white). */
function luminance(hex: string): number {
  const channels = [1, 3, 5].map(
    (i) => parseInt(hex.slice(i, i + 2), 16) / 255,
  );
  const [r, g, b] = channels.map((c) =>
    c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4,
  );
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

export function contrastRatio(a: string, b: string): number {
  const [light, dark] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (light + 0.05) / (dark + 0.05);
}
```

**src/app/tokens.test.ts**

```
// @vitest-environment node
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { contrastRatio } from "../../test/contrast";

const css = readFileSync(new URL("./globals.css", import.meta.url), "utf8");

/** Read the --name: #hex pairs inside a CSS block such as ":root { ... }". */
function tokens(selector: string): Record<string, string> {
  const block = css.match(new RegExp(`${selector}\\s*{([^}]*)}`))?.[1] ?? "";
  return Object.fromEntries(
    [...block.matchAll(/--([\w-]+):\s*(#[0-9a-fA-F]{6})/g)].map((m) => [
      m[1],
      m[2],
    ]),
  );
}

// [foreground token, background token, minimum ratio, what it is]
const textPairs: [string, string, number][] = [
  ["foreground", "background", 4.5],
  ["card-foreground", "card", 4.5],
  ["muted-foreground", "background", 4.5],
  ["muted-foreground", "muted", 4.5],
  ["foreground", "muted", 4.5],
  ["accent-foreground", "accent", 4.5],
  ["primary-foreground", "primary", 4.5],
  ["destructive-foreground", "destructive", 4.5],
  ["primary", "background", 4.5], // links and icons drawn in the primary colour
  ["destructive", "background", 4.5], // error messages
];
// Borders of inputs and focus rings must stand out from the page (WCAG 1.4.11).
const boundaryPairs: [string, string, number][] = [
  ["input", "background", 3],
  ["ring", "background", 3],
];

describe.each([":root", "\\.dark"])("colour tokens in %s", (selector) => {
  const t = tokens(selector);

  it("defines every token we check", () => {
    for (const [fg, bg] of [...textPairs, ...boundaryPairs]) {
      expect(t[fg], fg).toBeDefined();
      expect(t[bg], bg).toBeDefined();
    }
  });

  it.each(textPairs)(
    "%s on %s has contrast of at least %s:1",
    (fg, bg, min) => {
      expect(contrastRatio(t[fg], t[bg])).toBeGreaterThanOrEqual(min);
    },
  );

  it.each(boundaryPairs)("%s against %s has at least %s:1", (fg, bg, min) => {
    expect(contrastRatio(t[fg], t[bg])).toBeGreaterThanOrEqual(min);
  });
});

describe("the contrast helper", () => {
  it("knows the extremes", () => {
    expect(contrastRatio("#000000", "#ffffff")).toBeCloseTo(21, 0);
    expect(contrastRatio("#777777", "#777777")).toBe(1);
  });
});
```

The formula comes from the WCAG specification: each colour channel is converted to a *relative luminance*, and the ratio is `(lighter + 0.05) / (darker + 0.05)`. `describe.each` runs the same checks once for `:root` and once for `.dark`, and `it.each` turns each row of the table into its own named test, so a failure reads "muted-foreground on muted has contrast of at least 4.5:1", which tells you exactly what to fix. Notice the input border token: it is darker than the decorative `border` token on purpose, because the outline of a text box must be visible (3:1), while a card border may be subtle.


## Building a Component Library › Tests for the library

**src/components/ui/button.test.tsx**

```
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
```

**src/lib/utils.test.ts**

```
import { describe, expect, it } from "vitest";
import { cn } from "./utils";

describe("cn", () => {
  it("joins class names and skips falsy values", () => {
    expect(cn("a", false && "b", undefined, null, "c")).toBe("a c");
    expect(cn("a", { b: true, c: false })).toBe("a b");
  });

  it("lets the last conflicting Tailwind class win", () => {
    expect(cn("px-2 py-1", "px-4")).toBe("py-1 px-4");
    expect(cn("bg-primary text-sm", "bg-destructive")).toBe(
      "text-sm bg-destructive",
    );
  });

  it("keeps non-conflicting classes", () => {
    expect(cn("text-sm", "text-primary")).toBe("text-sm text-primary");
  });
});
```

The third Button test is the important one: a caller who passes `h-14` must *replace* the default `h-10`, not stack on top of it. The `asChild` test proves a link keeps its `href` and role while taking on button styles, and that no stray `<button>` exists.


## Responsive Layouts › Habits of responsive design

- **Design the phone first.** Start with the layout that has no prefixes, then add `sm:`, `md:`, `lg:` as space becomes available.
- **Use** `h-dvh`**, not** `h-screen`**,** for full-height layouts. On phones the browser’s address bar appears and disappears, and `dvh` follows the visible area.
- **Add** `min-h-0` **and** `min-w-0` **to flex children that scroll or contain long text.** By default a flex child refuses to shrink below its content, which is why a long conversation title can push a layout off the screen, or a chat refuse to scroll.
- **Make touch targets at least about 44 by 44 pixels.** Our `Button` is 40 px tall by default (`h-10`), and the icon button is `size-10`; for small, frequent controls on phones consider larger.
- **Never disable zoom** (`maximum-scale=1`). People with low vision rely on it. Next.js adds a correct viewport tag automatically.
- **Let text wrap and images scale** (`max-w-full`, `text-balance`), and test the narrowest screen (320 px) as well as your phone.
Resize your browser window slowly from wide to narrow and watch the pricing cards change from three columns to two to one (`sm:grid-cols-2 lg:grid-cols-3`), and the sidebar turn into a menu button. Your browser’s developer tools also have a **device toolbar** that simulates phone screens.


## Accessibility › Automated checks with axe

**axe-core** is the engine behind most accessibility tools (including those in browser developer tools). It inspects HTML and reports rule violations: missing labels, images without `alt`, buttons without names, invalid ARIA, duplicate ids. We run it inside our tests, so a regression fails the build.

**test/axe.ts**

```
import axe from "axe-core";

/**
 * Run the axe accessibility rules on a rendered component and return a list of
 * problems (empty means none). Colour contrast cannot be measured in jsdom,
 * so tokens.test.ts checks the palette numerically instead.
 */
export async function accessibilityProblems(container: Element) {
  const results = await axe.run(container, {
    rules: {
      "color-contrast": { enabled: false },
      region: { enabled: false }, // a lone component is not a whole page
    },
  });
  return results.violations.map(
    (v) =>
      `${v.id}: ${v.help} (${v.nodes.map((n) => n.target.join(" ")).join(", ")})`,
  );
}
```

**src/components/accessibility.test.tsx**

```
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
```

The last test checks the checker: it renders a deliberately broken form and confirms that axe reports the unlabeled input, the missing `alt` and the unnamed button. A test suite that can never fail proves nothing, so it is worth proving that this one can.

> **Automated tools find only part of the problems**
>
> axe can say "this button has no name", but not "this name is confusing" or "this layout is hard to follow". Colour contrast cannot be measured inside the simulated browser we use for tests, which is why we test the tokens numerically instead. Treat green axe results as the *minimum*, then test by hand: put the mouse away and use only Tab, Shift+Tab, Enter, Space, Escape and the arrow keys through every page; zoom the browser to 200 percent; and try a screen reader (VoiceOver on macOS and iOS, TalkBack on Android, NVDA on Windows) for a few minutes. Chrome’s Lighthouse panel also gives a quick accessibility score.


## Dates and Time Zones

In Chapter 18 we left timestamps out of the chat bubbles. Here is why, and how to add them. The API sends times in **UTC** (Chapter 8). A user in Lagos should see 10:30 for `09:30Z`, and a user in New York 4:30. But the server that renders the first HTML has its own time zone, usually UTC, and the user’s browser has another. If both render "the local time", the text differs, and React reports a **hydration mismatch** (Chapter 18, Section 18.3).

The fix is a two-phase component. On the server, and during the browser’s first render, it shows a stable UTC time with the zone named. Immediately after hydration it switches to the viewer’s own time zone. A tiny hook tells the component which phase it is in:

**src/hooks/useHydrated.ts**

```
"use client";

import { useSyncExternalStore } from "react";

const subscribe = () => () => {}; // nothing ever changes: we only need two phases

/** false on the server and while hydrating, true afterwards in the browser. */
export function useHydrated() {
  return useSyncExternalStore(
    subscribe,
    () => true,
    () => false,
  );
}
```

**src/components/LocalTime.tsx**

```
"use client";

import { useHydrated } from "@/hooks/useHydrated";

interface LocalTimeProps {
  iso: string; // an ISO 8601 timestamp in UTC, as sent by the API
  timeZone?: string; // defaults to the viewer's own time zone
  className?: string;
}

/**
 * Shows a UTC timestamp in the viewer's time zone without hydration errors:
 * the server (and the first browser render) show a stable UTC time, then the
 * browser switches to local time.
 */
export function LocalTime({ iso, timeZone, className }: LocalTimeProps) {
  const hydrated = useHydrated();
  const date = new Date(iso);
  const text = new Intl.DateTimeFormat("en", {
    hour: "numeric",
    minute: "2-digit",
    timeZone: hydrated ? timeZone : "UTC",
    timeZoneName: hydrated ? undefined : "short",
  }).format(date);
  return (
    <time dateTime={iso} className={className}>
      {text}
    </time>
  );
}
```

`useHydrated` uses the same `useSyncExternalStore` trick as `useLocalStorage`: its server value is `false` and its browser value is `true`, and React handles the switch cleanly. `Intl.DateTimeFormat` does the formatting and the time zone conversion with no library. The output is a semantic `<time dateTime="...">` element, which carries the exact value for machines and assistive technology.

**src/components/MessageBubble.tsx**

```
import { cn } from "@/lib/utils";
import type { Message } from "@/lib/types";
import { LocalTime } from "./LocalTime";

interface MessageBubbleProps {
  message: Pick<Message, "role" | "content"> & { createdAt?: string };
  pending?: boolean;
}

export function MessageBubble({
  message,
  pending = false,
}: MessageBubbleProps) {
  const isUser = message.role === "user";
  return (
    <div className={cn("flex", isUser ? "justify-end" : "justify-start")}>
      <div
        data-role={message.role}
        className={cn(
          "max-w-[85%] rounded-2xl px-4 py-2 text-sm whitespace-pre-wrap sm:max-w-[75%]",
          isUser
            ? "bg-primary text-primary-foreground"
            : "bg-muted text-foreground",
          pending && "opacity-60",
        )}
      >
        <p>{message.content}</p>
        {message.createdAt && !pending && (
          <LocalTime
            iso={message.createdAt}
            className="mt-1 block text-xs opacity-80"
          />
        )}
      </div>
    </div>
  );
}
```

**src/components/LocalTime.test.tsx**

```
import { render, screen } from "@testing-library/react";
import { renderToString } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { LocalTime } from "./LocalTime";

const iso = "2026-11-02T09:30:00Z";

describe("LocalTime", () => {
  it("renders a stable UTC time on the server, with the zone shown", () => {
    const html = renderToString(<LocalTime iso={iso} timeZone="Asia/Tokyo" />);
    expect(html).toContain("9:30");
    expect(html).toContain("UTC");
  });

  it("shows the viewer's own time zone in the browser", () => {
    render(<LocalTime iso={iso} timeZone="Africa/Lagos" />);
    expect(screen.getByText("10:30 AM")).toBeInTheDocument(); // Lagos is UTC+1
  });

  it("uses a real <time> element with the machine-readable value", () => {
    render(<LocalTime iso={iso} timeZone="America/New_York" />);
    const element = screen.getByText("4:30 AM"); // New York is UTC-5 in November
    expect(element.tagName).toBe("TIME");
    expect(element).toHaveAttribute("dateTime", iso);
  });
});
```

The tests pass an explicit `timeZone`, because tests that depend on the machine’s own zone pass on your laptop and fail on a build server. The first test uses `renderToString` from `react-dom/server`: it renders the component the way the server does, which is the only way to observe the server phase.

> **Store UTC, display local**
>
> Keep every timestamp in UTC in the database and in the API, and convert only at the last moment, in the user’s interface. For dates without a time (a birthday, a billing date) the time zone should not shift the day, so format those without converting. If you must compare or add days, use a library such as `date-fns` instead of doing arithmetic on milliseconds: days are not always 24 hours.
