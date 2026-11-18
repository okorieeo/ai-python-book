# Chapter 46 — Building the Web Frontend with Claude Code: extended material

The printed edition of *Building AI-Powered Apps* keeps each chapter short. This file holds the longer material that was moved here so that nothing is lost: the full hands-on lab, troubleshooting tables, checklists, further exercises, and sections that were condensed for print.


---

# Sections condensed for print


## What Changes When Claude Code Builds Your Frontend › What this chapter assumes about your backend

The frontend can only be as correct as the contract it talks to, and three earlier chapters made choices that this one cannot see from here. The table lists every assumption. If your backend differs, the right-hand column says which single file to change; nothing else should need to.

| **Assumption** | **Where it comes from** | **If yours differs, change** |
|---|---|---|
| Errors look like { "error": { "code", "message", "request_id", "fields" } } | Chapter 8 error format | toApiError() in src/lib/api/errors.ts |
| Login returns { access, user } and sets an HttpOnly refresh cookie. POST /auth/refresh/ returns a new access token | Chapter 13 | src/lib/auth/login.ts and the refresh function in client.ts |
| Lists are paginated as { count, next, previous, results } | Chapter 12 | The query hooks in src/lib/api/queries.ts |
| A WebSocket opens with a short-lived, single-use ticket from POST /chat/tickets/, and the server sends token, done and error frames | Chapter 14 | fetchSocketUrl() and src/lib/chat/protocol.ts |
| Too many requests return 429 with a Retry-After header. A spent daily token budget arrives as the error code budget_exceeded | Chapter 17 | friendlyMessage() and the ERROR_TEXT map in ChatWindow.tsx |


## Scaffolding a Next.js App and Encoding Your Design System › CLAUDE.md: the project’s memory

CLAUDE.md is read at the start of every session, so it is the cheapest place to put a rule that should hold forever. Run /init to generate a first version from your project, then prune it. The official guidance is a good test for each line: “Would removing this cause Claude to make mistakes?” If not, cut it. A long file makes Claude ignore half of it. Rules that apply only sometimes belong in a skill (see the new-component skill later in this section), which Claude loads on demand.

Here is the file we use. It is short on purpose, and every line exists because of a mistake covered in 46.8.

**CLAUDE.md**

```
# AI Chat frontend (Next.js App Router, TypeScript, Tailwind v4)

## Commands
- `npm run dev` starts the app on http://localhost:3000 (API on :8000)
- `npm run typecheck` and `npm test` must both pass before you say a task is done
- `npm run api:types` regenerates `src/lib/api/schema.d.ts` from
    `openapi/schema.yml`
- `npm run build` is the final check for anything that touches routes or config

## Architecture rules
- Server Components by default. Add `"use client"` only to the smallest component
    that needs state, effects or browser APIs.
- Every request to Django goes through `src/lib/api/client.ts`. Never call `fetch`
    for our API anywhere else.
- Never edit `src/lib/api/schema.d.ts` by hand: it is generated. If a type is wrong,
    the OpenAPI schema is wrong.
- Data fetching uses TanStack Query (`src/lib/api/queries.ts`), not `useEffect`.
- Forms use React Hook Form + a Zod schema in `src/lib/**/schemas.ts`.
- Server error text is never shown to users. Use `friendlyMessage()`.

## Design system
- Colors, radii and fonts live ONLY in `src/app/globals.css` tokens. Use semantic
    classes (`bg-background`, `text-muted-foreground`, `border-input`), never raw
    hex values or palette steps like `bg-blue-600`.
- Build on the primitives in `src/components/ui/`. Check there before writing a new
    button, input or label.
- Every interactive element needs a visible focus style and an accessible name.

## Gotchas
- `params` in route files is a Promise in this Next.js version: `const { id } =
    await params`.
- Model output is rendered with `react-markdown` WITHOUT `rehype-raw`. Never use
    `dangerouslySetInnerHTML`.
- Only `NEXT_PUBLIC_API_URL` and `NEXT_PUBLIC_WS_URL` are public. Never put a secret
    in a `NEXT_PUBLIC_*` variable.
- IMPORTANT: do not add dependencies without asking first. Say what the package does
    and why we cannot do it with what we have.
```

Two details are deliberate. The word IMPORTANT appears on exactly one line (emphasize everything and nothing stands out). And the rule "never edit schema.d.ts by hand" is advisory here; we make it enforceable with a hook below.


## Scaffolding a Next.js App and Encoding Your Design System › Primitives: the building blocks Claude reuses

Most Next.js projects use **shadcn/ui**, which is not a package but a command that copies component source files into your repository, so you own and can edit them. The usual way is to let Claude Code run the official CLI one component at a time:

**bash terminal**

```bash
npx shadcn@latest init
npx shadcn@latest add button input label textarea
```

Check the shadcn/ui documentation for the current prompts, because the CLI changes often. The zip for this chapter contains small hand-written equivalents of these four primitives, built with class-variance-authority and our tokens, so the code compiles without the CLI. Here is the button; the others follow the same pattern:

**src/components/ui/button.tsx**

```
import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 rounded-md text-sm font-medium
      transition-colors " +
    "focus-visible:outline-2 focus-visible:outline-offset-2
        focus-visible:outline-ring " +
    "disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground hover:opacity-90",
        outline: "border border-border bg-background hover:bg-muted",
        ghost: "hover:bg-muted",
      },
      size: {
        default: "h-10 px-4 py-2",
        sm: "h-9 px-3",
        icon: "h-10 w-10",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {}

export function Button({ className, variant, size, type = "button", ...props }:
    ButtonProps) {
  return <button type={type} className={cn(buttonVariants({ variant, size }),
      className)} {...props} />;
}
```

The reason to have primitives is not tidiness. It is that CLAUDE.md can now say "check src/components/ui before writing a new button", and Claude Code will reuse them instead of inventing a fifth variant.


## Scaffolding a Next.js App and Encoding Your Design System › Guardrails: hooks make rules deterministic

CLAUDE.md is advice, and Claude follows advice most of the time. A **hook** is a script that Claude Code runs at a fixed point in its workflow, every time, with no exceptions. Use CLAUDE.md for preferences and hooks for rules that must never be broken. Hooks live in .claude/settings.json (commit it, so the whole team gets them) and receive the details of the tool call as JSON on standard input. For a PreToolUse hook, **exit code 2 blocks the action** and sends your stderr message to Claude as the reason. Any other non-zero code only shows a warning and lets the action through.

**.claude/settings.json**

```
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [
          { "type": "command", "command": "node
              \"$CLAUDE_PROJECT_DIR/.claude/hooks/protect-files.mjs\"" }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          { "type": "command", "command": "node
              \"$CLAUDE_PROJECT_DIR/.claude/hooks/verify-before-stop.mjs\"",
              "timeout": 300 }
        ]
      }
    ]
  }
}
```

**.claude/hooks/protect-files.mjs**

```
// PreToolUse hook for Edit|Write. Exit code 2 blocks the edit and sends stderr to
    Claude.
import { readFileSync } from "node:fs";

const input = JSON.parse(readFileSync(0, "utf8"));
const filePath = String(input?.tool_input?.file_path ?? "").replaceAll("\\", "/");

const rules = [
  { test: (p) => p.endsWith("/src/lib/api/schema.d.ts"), why: "This file is
      generated. Change openapi/schema.yml (or the Django serializer) and run `npm
      run api:types`." },
  { test: (p) => /\/\.env(\.|$)/.test(p) && !p.endsWith(".env.example"), why:
      "Environment files hold secrets. Edit .env.example and ask the human to update
      the real file." },
  { test: (p) => p.endsWith("/package-lock.json"), why: "The lockfile is managed by
      npm. Run npm install instead of editing it." },
  { test: (p) => p.includes("/.git/"), why: "Never edit Git internals." },
];

const hit = rules.find((rule) => rule.test(filePath));
if (hit) {
  console.error(`Blocked: ${filePath}\n${hit.why}`);
  process.exit(2);
}
process.exit(0);
```

We wrote the hook in Node, not bash with jq, so it works the same on macOS, Linux and WSL without installing anything. We ran it with sample input exactly as Claude Code would send it:

| **Edit attempted on** | **Exit code** | **What Claude sees** |
|---|---|---|
| **src/lib/api/schema.d.ts** | 2 (blocked) | "This file is generated. Change openapi/schema.yml ... and run npm run api:types." |
| **.env and .env.local** | 2 (blocked) | "Environment files hold secrets. Edit .env.example ..." |
| **A Windows path ending in \.env** | 2 (blocked) | Same message (backslashes are normalized) |
| **.env.example** | 0 (allowed) | Nothing |
| **src/components/chat/Composer.tsx** | 0 (allowed) | Nothing |

Type /hooks in Claude Code to confirm the hook is registered. A good habit is to make the block message tell Claude what to do instead, as ours does, so it fixes the right thing rather than trying to get around the block.

> **A hook is a guardrail, not a sandbox**
>
> This hook watches the Edit and Write tools. A command run through the Bash tool (for example sed -i on a protected file) is a different tool and is not seen by it. Cover that gap with permission deny rules (/permissions), by not approving blanket shell access, and by reading the diff. Defense in depth again: no single layer is enough.


## Turning Wireframes and Screenshots into Components › Step 1: ask for an inventory, not code

**claude prompt (plan mode)**

```
[paste wireframe: chat-screen.png]

This is the chat screen for our AI Chat app. Do NOT write code yet.
1. List every component you would create, with a one-line purpose each.
2. For each, say which primitive in src/components/ui it reuses.
3. Say which components can be Server Components and which need "use client", and
    why.
4. List the states each component has (empty, loading, error, streaming).
Read CLAUDE.md and src/app/globals.css first.
```

Compare the answer with your wireframe. This five-minute review catches the expensive mistakes (a client component at the top of the tree, a missing empty state) before any code exists. For the chat screen the inventory should look like this:

| **Part of the wireframe** | **Component** | **Server or client?** | **States to handle** |
|---|---|---|---|
| **Left column of conversations** | ConversationList | Server-compatible (no state) | Empty, active item |
| **Scrolling message area** | MessageList | Client (scroll behavior) | Empty, streaming, busy |
| **Text box and send button** | Composer | Client (typing state) | Disabled, empty, too long |
| **Connection banner and errors** | ChatWindow | Client (owns the socket hook) | Connecting, reconnecting, error |
| **The whole screen** | ChatScreen | Client (TanStack Query) | Loading, failed, no selection |


## Turning Wireframes and Screenshots into Components › Step 3: check the result in a real browser

With a browser connected, Claude Code can open your running app, take a screenshot and compare it with the design, which closes the loop the way tests close it for logic. There are two common routes:

- **Claude in Chrome.** Install the Claude in Chrome extension (version 1.0.36 or later, in Chrome or Edge), then start Claude Code with claude --chrome, or run /chrome inside a session to check the connection. It needs a paid Claude plan. It can read console errors and the page structure and drive your logged-in browser.
- **An automation server over MCP**, such as Playwright’s. You add it with claude mcp add and Claude can then drive a browser it launches itself. Follow the server’s own README for the exact command, because it changes between releases.
**claude prompt**

```
The dev server is running on http://localhost:3000.
Open /chat in a browser, take a screenshot at widths 375, 768 and 1280, and compare
    each
with the wireframe. List every difference. Then check the browser console for
    errors.
Fix only the differences that affect layout or behavior, and show me the new
    screenshots.
```

The official guidance for this kind of work is the same as for tests: give Claude something to compare against and ask it to list the differences, then fix them. Look at the screenshots yourself. Claude Code is good at spotting a misaligned button and poor at noticing that a layout feels cramped.


## A Typed API Client from the OpenAPI Schema › Step 1: the backend publishes the schema

OpenAPI is the standard format for describing a REST API (Chapter 8). With drf-spectacular on the Django side, one command produces the file:

**bash terminal**

```bash
cd backend
python manage.py spectacular --file schema.yml --validate
cp schema.yml ../frontend/openapi/schema.yml
```

The file in this chapter’s zip is a hand-written sample in the shape that command produces, because no Django server was available when the chapter was written (see the box at the start). Here are two parts of it: the login operation and the error envelope every failure shares.

**openapi/schema.yml (login operation)**

```
  /api/v1/auth/login/:
    post:
      operationId: auth_login_create
      tags: [auth]
      security: []
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: "#/components/schemas/LoginRequest"
      responses:
        "200":
          description: Signed in. A refresh cookie is also set (HttpOnly).
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/LoginResponse"
        "400":
          description: Validation error
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/ErrorEnvelope"
        "401":
          description: Wrong email or password
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/ErrorEnvelope"
        "429":
          description: Too many attempts. See the Retry-After header.
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/ErrorEnvelope"
```

**openapi/schema.yml (error envelope)**

```
    ErrorBody:
      type: object
      properties:
        code:
          type: string
        message:
          type: string
        request_id:
          type: string
        fields:
          type: object
          additionalProperties:
            type: array
            items:
              type: string
      required: [code, message]
    ErrorEnvelope:
      type: object
      properties:
        error:
          $ref: "#/components/schemas/ErrorBody"
      required: [error]
```


## A Typed API Client from the OpenAPI Schema › The tests that keep it honest

The client has eight tests and the error helpers seven. Each one pins down a decision above. The client takes the underlying fetch function as an argument, so the tests run with a fake network and need no server:

| **Behavior** | **Test** |
|---|---|
| **Sends Authorization: Bearer <token>** | sends the access token as a Bearer header |
| **401, refresh, retry, success** | refreshes once on a 401 and retries the original request |
| **Three simultaneous 401s share one refresh** | shares ONE refresh between simultaneous 401s |
| **Refresh fails: session cleared** | gives up with the 401 when the refresh fails, and clears the token |
| **Wrong password does not trigger a refresh** | does not try to refresh when the LOGIN call itself returns 401 |
| **429 carries the wait time** | turns a 429 into an ApiError with retryAfter |
| **Offline** | reports a dropped connection as status 0 |
| **Retried POST keeps its body** | keeps the request body when it has to retry a POST |

To see that such tests really protect you, we ran an experiment. We changed refreshing ??= (async () => to refreshing = (async () =>, which removes the sharing, and ran the suite. Exactly one test failed: the one about simultaneous 401s. A test that cannot fail is worth nothing, so in 46.8 we make this check a habit.

**claude prompt**

```
Add src/lib/api/client.ts using openapi-fetch and the types in
    @src/lib/api/schema.d.ts.
Requirements: Bearer token from @src/lib/auth/session.ts; on 401 refresh once
    (shared between
concurrent requests) and retry; never refresh for the login/refresh endpoints;
    network
failures become ApiError status 0; errors parsed by toApiError in
    @src/lib/api/errors.ts.
Do NOT edit schema.d.ts. Write client.test.ts with a fake fetch covering: success,
    refresh and
retry, concurrent 401s (exactly one refresh), failed refresh, 429 with Retry-After,
    offline,
POST body preserved on retry. Run npm run typecheck && npm test and show me the
    output.
```

> **Where the access token lives**
>
> We keep it in a module variable (memory only), and the refresh token in an HttpOnly cookie that JavaScript cannot read. If a script injected through an XSS bug runs in the page, it can still call the API as the user, but it cannot steal a long-lived credential to use later. Chapter 17’s CORS and CSRF table explains why a token in the Authorization header needs no CSRF protection, while the cookie-based refresh call does (SameSite and exact allowed origins). Chapter 20 is the authority for your final auth design; the client is built so only session.ts and the refresh function change.


## Auth Flows and Forms › The form

**claude prompt**

```
Build LoginForm in src/components/auth/LoginForm.tsx with React Hook Form +
    zodResolver and
the schema in @src/lib/auth/schemas.ts. It receives onLogin(values) and onSuccess as
    props.
Behavior:
- Field errors appear under the field, tied to it with aria-describedby, and
    aria-invalid is set.
- A 400 with fields from the server puts each message on the matching input.
- ANY 401 shows the same sentence: "The email or password is incorrect." (Chapter
    17: uniform errors)
- A 429 says how many seconds to wait, using friendlyMessage() from
    @src/lib/api/errors.ts.
- The button is disabled and says "Signing in…" while the request runs.
- autocomplete attributes so password managers work. Use primitives from
    src/components/ui.
Write LoginForm.test.tsx for every bullet, including expectNoA11yViolations. Run the
    tests.
```

**src/components/auth/LoginForm.tsx**

```
"use client";

import { useId, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { ApiError, friendlyMessage } from "@/lib/api/errors";
import { loginSchema, type LoginValues } from "@/lib/auth/schemas";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

type Props = {
  onLogin: (values: LoginValues) => Promise<unknown>;
  onSuccess?: () => void;
};

export function LoginForm({ onLogin, onSuccess }: Props) {
  const id = useId();
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<LoginValues>({ resolver: zodResolver(loginSchema), defaultValues: {
      email: "", password: "" } });

  async function submit(values: LoginValues) {
    setFormError(null);
    try {
      await onLogin(values);
      onSuccess?.();
    } catch (error) {
      if (error instanceof ApiError && error.status === 400) {
        // Field-level messages from the server land on the matching inputs.
        for (const [name, messages] of Object.entries(error.fields)) {
          if (name === "email" || name === "password") {
            setError(name, { message: messages[0] ?? "Invalid value" });
          }
        }
        if (Object.keys(error.fields).length > 0) return;
      }
      // 401 is deliberately uniform: never say which of the two was wrong (17.11).
      setFormError(
        error instanceof ApiError && error.status === 401
          ? "The email or password is incorrect."
          : friendlyMessage(error),
      );
    }
  }

  const emailId = `${id}-email`;
  const passwordId = `${id}-password`;

  return (
    <form onSubmit={handleSubmit(submit)} noValidate className="flex w-full max-w-sm
        flex-col gap-4">
      <div className="flex flex-col gap-1.5">
        <Label htmlFor={emailId}>Email</Label>
        <Input
          id={emailId}
          type="email"
          autoComplete="email"
          aria-invalid={errors.email ? true : undefined}
          aria-describedby={errors.email ? `${emailId}-error` : undefined}
          {...register("email")}
        />
        {errors.email && (
          <p id={`${emailId}-error`} className="text-sm text-danger">
            {errors.email.message}
          </p>
        )}
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor={passwordId}>Password</Label>
        <Input
          id={passwordId}
          type="password"
          autoComplete="current-password"
          aria-invalid={errors.password ? true : undefined}
          aria-describedby={errors.password ? `${passwordId}-error` : undefined}
          {...register("password")}
        />
        {errors.password && (
          <p id={`${passwordId}-error`} className="text-sm text-danger">
            {errors.password.message}
          </p>
        )}
      </div>

      {formError && (
        <p role="alert" className="text-sm text-danger">
          {formError}
        </p>
      )}

      <Button type="submit" disabled={isSubmitting}>
        {isSubmitting ? "Signing in…" : "Sign in"}
      </Button>
    </form>
  );
}
```

What each server answer turns into, and the test that proves it:

| **Server answer** | **What the user sees** | **Test** |
|---|---|---|
| **Invalid input, client side** | Messages under each field, focus stays | shows field errors and does not call the server |
| **200** | onSuccess runs, the form sends trimmed values | submits trimmed values and calls onSuccess |
| **401 (any reason)** | "The email or password is incorrect." | uses the SAME message for any 401 |
| **400 with fields** | The message under the right input | puts server field errors on the matching input |
| **429 with Retry-After: 45** | "Too many attempts. Please try again in 45 seconds." | tells the user how long to wait after a 429 |
| **Request in progress** | Disabled button, "Signing in…" | disables the button while the request is in flight |
| **Anything** | No automatically detectable accessibility violations | has no automatically detectable accessibility violations |

**src/components/auth/LoginForm.test.tsx (excerpt)**

```
  it("uses the SAME message for any 401, so it never reveals which field was wrong",
      async () => {
    const onLogin = vi.fn().mockRejectedValue(new ApiError({ status: 401, code:
        "no_such_user", message: "No account with that email" }));
    render(<LoginForm onLogin={onLogin} />);
    await fill("ghost@example.com", "whatever");
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("The email or password is incorrect.");
    expect(alert).not.toHaveTextContent("No account");
  });
```


## A Streaming Chat UI › Step 4: the components

The UI is now the easy part, because everything hard is already tested. The window composes a message list and a composer and decides what to say when something is wrong:

**src/components/chat/ChatWindow.tsx**

```
"use client";

import { useChatStream, type SocketLike } from "@/lib/chat/useChatStream";
import type { ChatMessage } from "@/lib/chat/reducer";
import { Composer } from "./Composer";
import { MessageList } from "./MessageList";

type Props = {
  resolveUrl: () => Promise<string>;
  initialMessages?: ChatMessage[];
  socketFactory?: (url: string) => SocketLike;
};

// Messages for the codes the server can send. Anything else gets the generic
    sentence.
const ERROR_TEXT: Record<string, string> = {
  rate_limited: "You are sending messages too quickly. Wait a moment and try
      again.",
  budget_exceeded: "You have reached today's AI usage limit. It resets tomorrow.",
  connection_lost: "The connection dropped before the reply finished. You can send
      your message again.",
};

export function ChatWindow({ resolveUrl, initialMessages, socketFactory }: Props) {
  const { state, connection, send } = useChatStream({ resolveUrl, initialMessages,
      socketFactory });
  const streaming = state.status === "streaming";

  return (
    <section aria-label="Chat" className="flex h-full min-h-0 flex-col">
      {connection !== "open" && (
        <p role="status" className="bg-muted px-4 py-2 text-sm
            text-muted-foreground">
          {connection === "connecting" ? "Connecting…" : "Connection lost.
              Reconnecting…"}
        </p>
      )}
      <MessageList messages={state.messages} busy={streaming} />
      {state.error && (
        <p role="alert" className="px-4 py-2 text-sm text-danger">
          {ERROR_TEXT[state.error.code] ?? "Something went wrong. Please try
              again."}
        </p>
      )}
      <Composer onSend={send} disabled={connection !== "open" || streaming} />
    </section>
  );
}
```

The message list carries most of the accessibility work. It has role="log" and a name. It sets aria-busy while a reply is streaming, so a screen reader waits and reads the finished message instead of announcing every token. It keeps the view at the bottom, but only while the reader has not scrolled up. The markdown renderer loads on demand with next/dynamic, for a reason explained in 46.7.

**src/components/chat/MessageList.tsx**

```
"use client";

import { useEffect, useRef } from "react";
import dynamic from "next/dynamic";
import type { ChatMessage } from "@/lib/chat/reducer";
import { cn } from "@/lib/utils";

// The markdown renderer is the heaviest part of the chat bundle, and it is not
    needed
// until the first assistant message exists, so it loads on demand (46.7).
const Markdown = dynamic(() => import("./Markdown"), {
  loading: () => <span className="text-muted-foreground">…</span>,
});

export function MessageList({ messages, busy }: { messages: ChatMessage[]; busy:
    boolean }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const stickToBottom = useRef(true);

  useEffect(() => {
    const el = containerRef.current;
    if (el && stickToBottom.current) el.scrollTop = el.scrollHeight;
  }, [messages]);

  return (
    <div
      ref={containerRef}
      role="log"
      aria-label="Conversation"
      aria-busy={busy}
      onScroll={(event) => {
        const el = event.currentTarget;
        // If the reader scrolled up, stop pulling them back down while tokens
            arrive.
        stickToBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight <
            48;
      }}
      className="flex-1 overflow-y-auto p-4"
    >
      <ul className="mx-auto flex max-w-3xl flex-col gap-4">
        {messages.map((message) => (
          <li
            key={message.id}
            className={cn(
              "max-w-[85%] rounded-md px-4 py-2 text-sm leading-6",
              message.role === "user" ? "self-end bg-primary
                  text-primary-foreground" : "self-start bg-muted",
            )}
          >
            <span className="sr-only">{message.role === "user" ? "You said:" :
                "Assistant said:"}</span>
            {message.role === "assistant" ? (
              message.content ? (
                <Markdown>{message.content}</Markdown>
              ) : (
                <span className="text-muted-foreground">Thinking…</span>
              )
            ) : (
              <p className="whitespace-pre-wrap">{message.content}</p>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
```

The composer sends on Enter and adds a line on Shift+Enter, and it checks isComposing so that someone typing with an input method (Chinese, Japanese, Korean) can press Enter to confirm a character without sending half a message. Models rarely think of this unless you tell them.

**src/components/chat/Composer.tsx**

```
"use client";

import { useId, useState } from "react";
import { MAX_MESSAGE_LENGTH } from "@/lib/chat/protocol";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

type Props = { onSend: (content: string) => boolean; disabled: boolean };

export function Composer({ onSend, disabled }: Props) {
  const id = useId();
  const [value, setValue] = useState("");

  function submit() {
    if (onSend(value)) setValue("");
  }

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        submit();
      }}
      className="flex gap-2 border-t border-border p-3"
    >
      <label htmlFor={id} className="sr-only">
        Message
      </label>
      <Textarea
        id={id}
        rows={1}
        value={value}
        maxLength={MAX_MESSAGE_LENGTH}
        placeholder="Ask something…"
        disabled={disabled}
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={(event) => {
          // Enter sends, Shift+Enter adds a line. Never hijack Enter while an IME
              is composing.
          if (event.key === "Enter" && !event.shiftKey &&
              !event.nativeEvent.isComposing) {
            event.preventDefault();
            submit();
          }
        }}
      />
      <Button type="submit" disabled={disabled || value.trim() === ""}>
        Send
      </Button>
    </form>
  );
}
```

And the renderer for model output, which is the most security-sensitive file in the chapter. A model can be tricked into producing HTML or a javascript: link (prompt injection, Chapter 28), so we render it as markdown that cannot contain raw HTML:

**src/components/chat/Markdown.tsx**

```
import ReactMarkdown from "react-markdown";

// react-markdown does not render raw HTML and strips javascript: links by default.
// That is the property we rely on (17.7): never add rehype-raw to this component.
export default function Markdown({ children }: { children: string }) {
  return (
    <ReactMarkdown
      components={{
        a: ({ href, children: label }) => (
          <a href={href} target="_blank" rel="noopener noreferrer"
              className="text-primary underline">
            {label}
          </a>
        ),
        pre: ({ children: code }) => (
          <pre className="my-2 max-w-full overflow-x-auto rounded-md bg-muted p-3
              text-sm" tabIndex={0}>
            {code}
          </pre>
        ),
      }}
    >
      {children}
    </ReactMarkdown>
  );
}
```

The test feeds it a hostile reply and checks that no script or image element appears, that the link is not a javascript: URL and that nothing ran:

**src/components/chat/ChatWindow.test.tsx (excerpt)**

```
  it("renders model output as text, never as HTML or a javascript: link", async ()
      => {
    const { socket, container } = await renderChat();
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Message"), "x{Enter}");
    act(() =>
      socket.receive({
        type: "token",
        delta: '<img src=x onerror="window.pwned=1"> <script>window.pwned=1</script>
            [click](javascript:window.pwned=1)',
      }),
    );
    await screen.findByText("click");
    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector("img")).toBeNull();
    const link = screen.getByText("click").closest("a");
    expect(link?.getAttribute("href") ?? "").not.toMatch(/^javascript:/i);
    expect((window as unknown as { pwned?: number }).pwned).toBeUndefined();
  });
```

We checked this test too. We temporarily installed rehype-raw and enabled it in Markdown.tsx, which tells the renderer to trust raw HTML, and the test failed with "expected <script></script> to be null". Then we removed it.

> **Test with a real screen reader**
>
> Automated checks find the mistakes a machine can see: missing labels, wrong roles, bad structure. They cannot tell you whether the streaming experience makes sense when spoken. Spend ten minutes with VoiceOver (macOS and iOS), NVDA (Windows, free) or TalkBack (Android) on the chat screen. Whether aria-busy gives a better experience than a live region for your users is a judgment you can only make by listening.


## Reviewing for Accessibility, Responsiveness and Performance › A real finding: the border that was too faint

Here are the contrast ratios of the design tokens, calculated from their color values with the WCAG formula. Text needs at least 4.5 to 1. The boundary of a control (an input’s border) needs at least 3 to 1 under WCAG 1.4.11, because someone with low vision must be able to see where the box is.

| **Pair** | **Light** | **Dark** | **Needs** | **Result** |
|---|---|---|---|---|
| **Text on background** | 17.74 | 17.01 | 4.5 | Pass |
| **Muted text on background** | 7.56 | 7.37 | 4.5 | Pass |
| **Muted text on muted surface** | 6.87 | 5.78 | 4.5 | Pass |
| **Button text on primary** | 6.70 | 5.09 | 4.5 | Pass |
| **Error text on background** | 6.47 | 6.77 | 4.5 | Pass |
| **Input border, first version (--border)** | 1.47 | 1.82 | 3.0 | FAIL |
| **Input border, fixed (--input)** | 4.83 | 5.09 | 3.0 | Pass |

The first version used the same light gray for dividers and for input borders, which is the default in many shadcn/ui setups. Our tests did not catch it and the design looked clean. The fix was a separate token, --input, that is darker, and a change to the input and textarea classes (border-input). This is exactly the kind of decision to turn into a rule in CLAUDE.md, which is why the file says to use border-input.

> **Still measure in a browser**
>
> These ratios come from the color values, not from rendered pages. Run Lighthouse or your browser’s accessibility inspector on the real screens, in both themes, before you ship. No real browser was available when this chapter was written, so that step is yours.


## Reviewing for Accessibility, Responsiveness and Performance › Layer 2: a reviewer with fresh eyes

A reviewer that did not write the code is not biased toward it. Claude Code supports this with **subagents**: specialized assistants, defined in .claude/agents/, that run in their own context with their own tool list and report back a summary. Ours may read and run commands but not edit, which is what you want from a reviewer.

**.claude/agents/frontend-reviewer.md**

```
---
name: frontend-reviewer
description: Reviews frontend changes for accessibility, responsiveness, performance
    and our own rules. Use after finishing a component or page, before committing.
tools: Read, Grep, Glob, Bash
---
You review a Next.js frontend diff. You have not seen how it was written, so judge
    only what is in front of you. You never edit files.

Start with `git diff` and `git status`, then read each changed file in full and
    CLAUDE.md.

Check, in this order:
1. Correctness against the stated requirement. Say which requirement each change
    satisfies.
2. Our rules in CLAUDE.md: Server Components by default, one API client, no
    hand-edited generated files, no raw colors, no `dangerouslySetInnerHTML`, no
    secrets in `NEXT_PUBLIC_*`.
3. Accessibility: every control has an accessible name, form errors are tied to
    inputs with `aria-describedby`, focus is visible, headings are in order, status
    changes use `role="status"` or `role="alert"`, nothing depends on color alone.
4. Responsiveness: nothing overflows at 320px wide, touch targets are at least 40px,
    no fixed heights that clip text.
5. Performance: needless `"use client"`, large imports that could load on demand,
    effects that fetch data, lists without stable keys.

Report only gaps that affect correctness, accessibility or the stated requirements.
    For each: the file and line, what is wrong, and the smallest fix. If you find
    nothing, say so plainly. Do not suggest style preferences or extra abstractions.
```

**claude prompt**

```
Use the frontend-reviewer subagent to review my uncommitted changes against the
requirements in PLAN.md. Report gaps that affect correctness, accessibility or the
    stated
requirements. Ignore style preferences.
```

The last instruction in both the agent file and the prompt is not decoration. A reviewer that is asked to find problems will usually find some, even in sound work, and chasing every finding leads to over-engineering: extra abstraction layers, defensive code for cases that cannot happen, tests for the impossible. Tell it to report only real gaps and treat the rest as optional.


## Reviewing for Accessibility, Responsiveness and Performance › Performance: do less, send less

The best performance tactics are decisions made earlier in this chapter. Server Components by default send no JavaScript for what they render. System fonts remove a request and a layout shift. TanStack Query replaces hand-written effects that fetch twice. One decision is worth measuring.

The markdown renderer (react-markdown and everything it pulls in to parse) is the heaviest part of the chat code, and nothing needs it until the first assistant message exists. MessageList therefore loads it with next/dynamic. We built the project and measured: the renderer is in its own file of about 116 KB (about 35 KB compressed with gzip), and no other output file contains the markdown parser. Remove the dynamic call and that code moves into the main bundle of every visitor, including the login page.

**src/components/chat/MessageList.tsx (excerpt)**

```
// The markdown renderer is the heaviest part of the chat bundle, and it is not
    needed
// until the first assistant message exists, so it loads on demand (46.7).
const Markdown = dynamic(() => import("./Markdown"), {
  loading: () => <span className="text-muted-foreground">…</span>,
});
```

Two other measurements to take on the finished site, not in your head: run Lighthouse against the production build (npm run build, then npm start) and watch the three Core Web Vitals. Google’s thresholds for a "good" result are Largest Contentful Paint at 2.5 seconds or less, Interaction to Next Paint at 200 milliseconds or less, and Cumulative Layout Shift at 0.1 or less.

**bash terminal**

```bash
npm run build && npm start
# in a second terminal:
npx lighthouse http://localhost:3000/login
    --only-categories=performance,accessibility --view
```


## Reviewing for Accessibility, Responsiveness and Performance › Make "done" mean something: a Stop hook

Claude sometimes ends a turn with the build broken. A **Stop hook** runs when Claude is about to finish, and exit code 2 stops it from finishing and sends your message back as its next instruction. Ours runs the typecheck and the tests, but only when files under src changed, so a pure question does not trigger a test run. It checks stop_hook_active to avoid trapping Claude in a loop, and Claude Code itself gives up after eight consecutive blocks.

**.claude/hooks/verify-before-stop.mjs**

```
// Stop hook: Claude may not finish a turn while typecheck or tests fail.
// Exit code 2 keeps Claude working and sends stderr back to it.
import { readFileSync } from "node:fs";
import { spawnSync } from "node:child_process";

const input = JSON.parse(readFileSync(0, "utf8"));
if (input.stop_hook_active) process.exit(0); // already retrying once: never loop
    forever

// Skip the check on turns that did not touch source files (a pure question, for
    example).
const status = spawnSync("git", ["status", "--porcelain", "--", "src"], { encoding:
    "utf8" });
if (status.status === 0 && status.stdout.trim() === "") process.exit(0);

const checks = [
  ["typecheck", ["run", "typecheck"]],
  ["tests", ["test"]],
];
for (const [name, args] of checks) {
  const result = spawnSync("npm", args, { encoding: "utf8" });
  if (result.status !== 0) {
    const tail =
        `${result.stdout}\n${result.stderr}`.trim().split("\n").slice(-40).join("\n"
        );
    console.error(`You are not done: \`npm ${args.join(" ")}\` failed (${name}). Fix
        the cause, then run it again.\n\n${tail}`);
    process.exit(2);
  }
}
process.exit(0);
```

We ran it in four situations:

| **Situation** | **Exit code** | **Result** |
|---|---|---|
| **No changes under src** | 0 | Skipped; Claude finishes normally |
| **A test broken on purpose (a changed validation message)** | 2 | "You are not done: npm test failed (tests). Fix the cause..." plus the last lines of output |
| **Same, but stop_hook_active is true** | 0 | Allowed through, so it can never loop forever |
| **Test fixed** | 0 | Claude finishes |


## What Claude Code Gets Wrong in Frontend Work › The mutation check

For any test Claude writes, ask one question: **would this fail if the code were wrong?** The way to find out is to break the code on purpose and run the test. We did this three times while writing this chapter, and you can do it in two minutes whenever you doubt a test:

| **Planted bug** | **File** | **Test that caught it** |
|---|---|---|
| **Refresh not shared between simultaneous 401s** | client.ts | shares ONE refresh between simultaneous 401s |
| **Stray token appended after done** | reducer.ts | ignores a stray token that arrives after done |
| **Markdown renders raw HTML** | Markdown.tsx | renders model output as text, never as HTML or a javascript: link |

**claude prompt**

```
For each test file you just wrote, do a mutation check. Pick two behaviors the code
implements, break each one on purpose (comment out the guard, flip the condition),
    run the tests,
and confirm a test fails. Then restore the code with git checkout. Show me which
    test caught
which change. If a mutation survives, the tests are too weak: fix them.
```
