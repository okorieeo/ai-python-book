# Chapter 18 — React and Next.js Fundamentals: extended material

The printed edition of *Building AI-Powered Apps* keeps each chapter short. This file holds the longer material that was moved here so that nothing is lost: the full hands-on lab, troubleshooting tables, checklists, further exercises, and sections that were condensed for print.


---

# Sections condensed for print


## The JavaScript and TypeScript You Need

React is just JavaScript with a few new ideas. If you already write Python, most of this will feel familiar with different punctuation. Here are the pieces that appear on almost every line of a React program.

**typescript**

```typescript
// const cannot be reassigned; let can. Prefer const.
const name = "Ada";
let count = 0;

// Functions: the arrow form is everywhere in React.
function add(a: number, b: number): number { return a + b; }
const double = (n: number) => n * 2;

// Objects and arrays, and "destructuring" to unpack them.
const user = { id: 7, name: "Ada", role: "member" };
const { name: userName, role } = user;     // userName = "Ada", role = "member"
const [first, second] = ["a", "b", "c"];   // first = "a", second = "b"

// Spread: copy an object or array and change one part. React uses this constantly.
const admin = { ...user, role: "admin" };       // a NEW object; user is untouched
const more = [...["a", "b"], "c"];              // a NEW array: ["a", "b", "c"]

// Array methods that replace loops.
const prices = [1900, 0, 4900];
prices.map((p) => p / 100);          // [19, 0, 49]
prices.filter((p) => p > 0);         // [1900, 4900]
prices.find((p) => p === 0);         // 0
prices.some((p) => p > 4000);        // true

// Optional chaining and nullish coalescing: safe access with a default.
const title = conversation?.title ?? "Untitled";   // "Untitled" if missing or null

// Modules: every file is a module.
import { formatPrice } from "@/lib/format";   // "@/" means the src/ folder
export function helper() {}                    // a named export
export default function Page() {}              // one default export per file

// Promises and async/await: code that waits (network, disk) without freezing.
async function load(id: string) {
  const response = await fetch(`/api/conversations/${id}`);
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return (await response.json()) as { title: string };
}
```

**TypeScript** adds a layer of *types* on top. Types cost almost nothing to write and catch whole classes of mistakes:

**typescript**

```typescript
interface Message {                    // the shape of an object
  id: number;
  role: "user" | "assistant";          // a "union": only these two strings are allowed
  content: string;
  createdAt: string;
}

function show(message: Message) {}     // the compiler checks every call

show({ id: 1, role: "admin", content: "Hi", createdAt: "" });
//                   ^^^^^^^ error: "admin" is not assignable to "user" | "assistant"

type Pending = Pick<Message, "role" | "content">;   // build a type from another
const maybe: string | null = null;                   // "string or null" must be handled
```

> **Types disappear at runtime**
>
> TypeScript is checked when you build, then erased. A type does not validate data that arrives from the network: `(await response.json()) as Message` is a *promise to the compiler*, not a check. Anything from outside your program (API responses, form input, `localStorage`) must still be validated at runtime, as our route handler does in Section 18.7.


## Effects, Refs and External Stores › Reading from `localStorage` without breaking the page

We want the chat box to remember an unsent draft, even after a refresh. That means reading `localStorage`, which exists only in the browser. But Next.js renders components **on the server first**, then **hydrates** them in the browser: React attaches itself to the HTML that is already there and expects its first browser render to produce *exactly the same HTML*. If the server renders an empty box and the browser immediately renders the saved draft, React reports a *hydration mismatch*.

The naive fixes (check `typeof window`, or set state inside an effect) either cause the mismatch or cause a flash and an extra render. The correct tool is `useSyncExternalStore`, which is made for subscribing to a store that lives outside React. You give it a way to subscribe, a way to read the current value, and a separate value to use on the server:

**src/hooks/useLocalStorage.ts**

```
"use client";

import { useCallback, useSyncExternalStore } from "react";

const CHANGE_EVENT = "local-storage-change";

function subscribe(callback: () => void) {
  window.addEventListener("storage", callback); // changes from other tabs
  window.addEventListener(CHANGE_EVENT, callback); // changes from this tab
  return () => {
    window.removeEventListener("storage", callback);
    window.removeEventListener(CHANGE_EVENT, callback);
  };
}

/**
 * A string kept in localStorage. It renders `initial` on the server and during
 * hydration, then switches to the stored value, so the HTML always matches.
 */
export function useLocalStorage(key: string, initial: string) {
  const value = useSyncExternalStore(
    subscribe,
    () => {
      try {
        return window.localStorage.getItem(key) ?? initial;
      } catch {
        return initial; // storage blocked (private mode, strict settings)
      }
    },
    () => initial, // what the server renders
  );

  const setValue = useCallback(
    (next: string) => {
      try {
        window.localStorage.setItem(key, next);
      } catch {
        /* ignore: the draft simply will not be remembered */
      }
      window.dispatchEvent(new Event(CHANGE_EVENT));
    },
    [key],
  );

  return [value, setValue] as const;
}
```

Our own hook, `useLocalStorage`, is a **custom hook**: an ordinary function that calls other hooks, so several components can share the logic. During server rendering and hydration React uses the third argument (`() => initial`), so the HTML matches; right after hydration it switches to the stored value. Writing dispatches a small custom event so that every component using the same key updates, and the browser’s own `storage` event keeps other tabs in sync. The `try/catch` handles browsers that block storage entirely.

> **Other common sources of hydration errors**
>
> Anything that differs between server and browser during the first render: `Date.now()`, `Math.random()`, dates formatted in the viewer’s time zone, `window.innerWidth`, and invalid HTML nesting such as a `<div>` inside a `<p>`. This is why our message bubbles show no timestamps yet: the server’s time zone and the user’s differ. Chapter 19 shows a safe way to display local times.


## A Real Component: the Chat Panel › Optimistic updates

When the user presses Send, waiting a second for the server before anything appears feels broken. An **optimistic update** shows the message immediately, assuming the server will accept it, and corrects the screen if it does not. Look at the three outcomes in `handleSubmit`:

| **Moment** | **What the code does** | **What the user sees** |
|---|---|---|
| **Before the request** | Adds a temporary message with a **negative id**; clears the box; sets `sending` | Their message, slightly faded, and "The assistant is typing…" |
| **Success (2xx)** | Removes the temporary message; adds the server’s real user message and the assistant’s answer | The faded message becomes solid; the answer appears |
| **Failure (network or 4xx/5xx)** | Removes the temporary message; **puts the text back** in the box; shows an error | Nothing was lost, and a message says to try again |

Other details deserve a second look. The updater form `setMessages((current) => [...])` always works from the latest state, which matters when updates overlap. `finally` ensures `sending` is turned off whatever happens. The button is disabled while sending, so a double click cannot send twice, and when the draft contains only spaces. `event.currentTarget.form?.requestSubmit()` makes the Enter key behave exactly like clicking Send, including form validation, while Shift+Enter inserts a new line.

> **Optimistic updates need a way back**
>
> Showing a result before it is confirmed is a promise. Every optimistic update must have a rollback path, and the rollback must give the user’s work back. Losing a long message on a flaky mobile connection is a reason to stop using a product. Our test `undoes the optimistic message and restores the text when sending fails` pins this behavior down.


## Data Fetching, Streaming and Caching › What the build tells you

`next build` prints how each route will be served. Reading this table is the quickest way to check that your pages behave as intended:

**terminal**

```bash
npm run build
 example output
Route (app)
┌ ○ /
├ ○ /_not-found
├ ƒ /api/conversations
├ ƒ /api/conversations/[id]/messages
├ ○ /chat
├   /chat/[id]
│ └ ◐ /chat/[id]
└ ○ /pricing

○  (Static)             prerendered as static content
◐  (Partial Prerender)  prerendered as static HTML with dynamic server-streamed content
ƒ  (Dynamic)            server-rendered on demand
```

The landing, pricing and chat home pages are fully **static**. `/chat/[id]` is **partially prerendered**: the layout and skeleton are static and the conversation is streamed. The API routes are **dynamic**.

> **A streamed 404 still has status 200**
>
> Once a page starts streaming, the HTTP status line has already been sent, so it cannot become `404`. Visit `/chat/does-not-exist` and you get our friendly not-found page, but the status code is `200`, with a `noindex` tag so search engines ignore it. This is documented behavior. For a public page where a real `404` matters (a blog post), call `notFound()`  *before* any `await` or Suspense boundary. For a page behind a login, like ours, the difference is harmless.


## Testing React Components

Tests let you change a component with confidence. The philosophy of **Testing Library**, which we use with **Vitest**, is to test what a *user* experiences: find things by their role and visible text, click and type as a user would, and check what appears. Tests written this way survive refactoring, because they do not care how the component is built inside.

**vitest.config.mts**

```
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

const src = (path: string) => fileURLToPath(new URL(path, import.meta.url));

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": src("./src"),
      "server-only": src("./test/server-only.ts"), // a no-op in tests
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
```

**test/setup.ts**

```
import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, beforeEach } from "vitest";

// Files marked `@vitest-environment node` have no `window`, so guard for it.
const inBrowserLikeEnvironment = typeof window !== "undefined";

beforeEach(() => {
  if (!inBrowserLikeEnvironment) return;
  // jsdom does not implement scrollIntoView, so give components a harmless stand-in.
  window.HTMLElement.prototype.scrollIntoView = () => {};
  window.localStorage.clear();
});
afterEach(() => {
  if (inBrowserLikeEnvironment) cleanup();
});
```

| **Query** | **Finds** | **Use it when** |
|---|---|---|
| `getByRole("button", { name: "Send" })` | An element by its accessibility role and name | First choice for almost everything |
| `getByLabelText("Message")` | A form control by its label | Inputs and text areas |
| `getByText("Hello")` | An element by its visible text | Content |
| `findBy...` | The same, but **waits** for it to appear | After an async action |
| `queryBy...` | Returns `null` instead of failing | Asserting that something is **not** there |

Queries by role double as an **accessibility check**: if a button cannot be found by its role and name, a screen reader user cannot find it either. The tests below follow one pattern, *arrange, act, assert*, and each reads as a sentence.

**src/components/ChatPanel.test.tsx**

```
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
```

Study the third test. It replaces `fetch` with a function whose result we control, types and clicks like a user, and checks the message appears **before** the server answers. Then it resolves the pending request and checks that the answer arrives and nothing is duplicated. Controlling the timing of the fake server is what makes a test about *in-between states* possible.

**src/components/PricingTable.test.tsx**

```
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { plans } from "@/lib/plans";
import { PricingTable } from "./PricingTable";

describe("PricingTable", () => {
  it("renders one card per plan, with the popular one marked", () => {
    render(<PricingTable plans={plans} />);
    expect(screen.getAllByRole("article")).toHaveLength(3);
    expect(screen.getAllByText("Most popular")).toHaveLength(1);
    const pro = screen
      .getByRole("heading", { name: "Pro" })
      .closest("article")!;
    expect(within(pro).getByText("Most popular")).toBeInTheDocument();
  });

  it("shows monthly prices first, and free plans have no interval", () => {
    render(<PricingTable plans={plans} />);
    expect(screen.getByText("$19.00")).toBeInTheDocument();
    expect(screen.getAllByText(/\/ month/)).toHaveLength(2);
    expect(screen.getByText("$0.00")).toBeInTheDocument();
  });

  it("switches every card to yearly prices when the box is ticked", async () => {
    const user = userEvent.setup();
    render(<PricingTable plans={plans} />);
    await user.click(screen.getByRole("checkbox", { name: /bill yearly/i }));
    expect(screen.getByText("$190.00")).toBeInTheDocument();
    expect(screen.getByText("$490.00")).toBeInTheDocument();
    expect(screen.getAllByText(/\/ year/)).toHaveLength(2);
  });
});
```

**src/components/NavComponents.test.tsx**

```
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
```

`NavComponents.test.tsx` mocks `next/navigation`, because `useRouter` and `usePathname` only work inside a running Next.js app. Mocking a boundary you do not own, and asserting on how your code calls it (`push` was called with `/chat/abc`), is the standard approach.

**src/hooks/useLocalStorage.test.ts**

```
import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { useLocalStorage } from "./useLocalStorage";

describe("useLocalStorage", () => {
  it("returns the initial value when nothing is stored", () => {
    const { result } = renderHook(() => useLocalStorage("k", "start"));
    expect(result.current[0]).toBe("start");
  });

  it("reads an existing value", () => {
    window.localStorage.setItem("k", "saved");
    const { result } = renderHook(() => useLocalStorage("k", "start"));
    expect(result.current[0]).toBe("saved");
  });

  it("writes through to storage and re-renders", () => {
    const { result } = renderHook(() => useLocalStorage("k", ""));
    act(() => result.current[1]("hello"));
    expect(result.current[0]).toBe("hello");
    expect(window.localStorage.getItem("k")).toBe("hello");
  });

  it("keeps two hooks with the same key in sync", () => {
    const a = renderHook(() => useLocalStorage("shared", ""));
    const b = renderHook(() => useLocalStorage("shared", ""));
    act(() => a.result.current[1]("from a"));
    expect(b.result.current[0]).toBe("from a");
  });
});
```

**src/components/MessageBubble.test.tsx**

```
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
```


### Testing Server Components and route handlers

A Server Component is an `async` function, so you test it by **calling it, awaiting the result, and rendering that**. A route handler is a function from `Request` to `Response`, so you call it directly with a `Request` you build; no server is needed. The `@vitest-environment node` comment at the top switches those files to Node instead of a fake browser.

**src/app/(app)/chat/[id]/page.test.tsx**

```
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import ConversationPage from "./page";

// A Server Component is an async function: call it, await it, render what it returns.
const open = (id: string) =>
  ConversationPage({ params: Promise.resolve({ id }) } as never);

describe("the conversation page", () => {
  it("loads the conversation on the server and hands its messages to the chat", async () => {
    render(await open("welcome"));
    expect(screen.getByText("What can you help me with?")).toBeInTheDocument();
    expect(screen.getByLabelText("Message")).toBeInTheDocument();
  });

  it("renders the not-found page for an unknown id", async () => {
    await expect(open("does-not-exist")).rejects.toMatchObject({
      digest: expect.stringContaining("404"),
    });
  });
});
 src/app/api/conversations/[id]/messages/route.test.ts
// @vitest-environment node
import { describe, expect, it } from "vitest";
import { createConversation } from "@/lib/data";
import { POST } from "./route";

const call = async (id: string, body: string) => {
  const request = new Request("http://localhost/api/conversations/x/messages", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
  });
  return POST(request, { params: Promise.resolve({ id }) } as never);
};

describe("POST /api/conversations/{id}/messages", () => {
  it("creates the message and the answer", async () => {
    const { id } = await createConversation();
    const response = await call(
      id,
      JSON.stringify({ content: "  Hi there  " }),
    );
    expect(response.status).toBe(201);
    const data = await response.json();
    expect(data.userMessage.content).toBe("Hi there"); // trimmed
    expect(data.assistantMessage.role).toBe("assistant");
  });

  it("rejects blank or oversized content with the standard error format", async () => {
    const { id } = await createConversation();
    for (const content of ["   ", "x".repeat(8001), 42]) {
      const response = await call(id, JSON.stringify({ content }));
      expect(response.status).toBe(422);
      const { error } = await response.json();
      expect(error.code).toBe("validation_error");
      expect(error.details.content).toBeDefined();
      expect(error.request_id).toMatch(/^req_/);
    }
  });

  it("rejects bodies that are not JSON", async () => {
    const { id } = await createConversation();
    const response = await call(id, "not json");
    expect(response.status).toBe(400);
    expect((await response.json()).error.code).toBe("invalid_json");
  });

  it("returns 404 for an unknown conversation", async () => {
    const response = await call("missing", JSON.stringify({ content: "Hi" }));
    expect(response.status).toBe(404);
  });
});
```

**src/lib/data.test.ts**

```
// @vitest-environment node
import { describe, expect, it } from "vitest";
import {
  addMessage,
  createConversation,
  getConversation,
  listConversations,
} from "./data";

describe("the mock data layer", () => {
  it("starts with seeded conversations", async () => {
    const list = await listConversations();
    expect(list.map((c) => c.id)).toEqual(
      expect.arrayContaining(["welcome", "invoices"]),
    );
  });

  it("creates a conversation with a default title", async () => {
    const created = await createConversation("   ");
    expect(created.title).toBe("New conversation");
    expect((await getConversation(created.id))?.messages).toEqual([]);
  });

  it("adds the user's message and an answer, with increasing ids", async () => {
    const { id } = await createConversation();
    const result = await addMessage(id, "Hello");
    expect(result?.userMessage).toMatchObject({
      role: "user",
      content: "Hello",
    });
    expect(result?.assistantMessage).toMatchObject({
      role: "assistant",
      content: "Echo: Hello",
    });
    expect(result!.assistantMessage.id).toBeGreaterThan(result!.userMessage.id);
    expect((await getConversation(id))?.messages).toHaveLength(2);
  });

  it("returns null for unknown conversations", async () => {
    expect(await getConversation("nope")).toBeNull();
    expect(await addMessage("nope", "Hi")).toBeNull();
  });
});
```

**src/lib/format.test.ts**

```
import { describe, expect, it } from "vitest";
import { formatPrice, formatTokens } from "./format";
import { yearlyPriceCents } from "./plans";

describe("formatPrice", () => {
  it("turns integer cents into a currency string", () => {
    expect(formatPrice(1900)).toBe("$19.00");
    expect(formatPrice(0)).toBe("$0.00");
    expect(formatPrice(4999)).toBe("$49.99");
  });
});

describe("formatTokens", () => {
  it("uses K and M for large numbers", () => {
    expect(formatTokens(50_000)).toBe("50K tokens");
    expect(formatTokens(1_000_000)).toBe("1M tokens");
    expect(formatTokens(800)).toBe("800 tokens");
  });
});

describe("yearlyPriceCents", () => {
  it("charges ten months for twelve", () => {
    expect(yearlyPriceCents(1900)).toBe(19_000);
  });
});
```

> **What these tests cannot see**
>
> Component tests run in a simulated browser (jsdom). They do not catch layout bugs, real browser differences or whole-journey problems. For those, Chapter 39 adds end-to-end tests that drive a real browser. Use many fast component tests and a few end-to-end ones.
