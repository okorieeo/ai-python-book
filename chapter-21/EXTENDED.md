# Chapter 21 — Real-Time and AI Interfaces in the Browser: extended material

The printed edition of *Building AI-Powered Apps* keeps each chapter short. This file holds the longer material that was moved here so that nothing is lost: the full hands-on lab, troubleshooting tables, checklists, further exercises, and sections that were condensed for print.


---

# Sections condensed for print


## Validating Messages with Zod

Everything that arrives over the socket is **input from the network**. A bug on the server, a proxy that injects a message, or an attacker who can reach the socket could send something unexpected, and our code must not crash or misbehave. So every message is parsed and validated before anything uses it. We use Zod, which you met in Chapter 20, to describe each message once and get TypeScript types for free:

**src/lib/realtime/protocol.ts**

```
import { z } from "zod";

// The wire format lives in ONE file. If the backend changes, only this file changes.

const id = z.string().min(1);

const messageSchema = z.object({
  id,
  role: z.enum(["user", "assistant"]),
  content: z.string(),
  created_at: z.string(),
});

export const serverEventSchema = z.discriminatedUnion("type", [
  z.object({
    type: z.literal("message.accepted"),
    conversation_id: id,
    client_id: id,
    message: messageSchema,
  }),
  z.object({
    type: z.literal("assistant.start"),
    conversation_id: id,
    message_id: id,
    created_at: z.string().optional(),
  }),
  z.object({
    type: z.literal("assistant.delta"),
    message_id: id,
    delta: z.string(),
  }),
  z.object({
    type: z.literal("assistant.end"),
    message_id: id,
    finish_reason: z.enum(["stop", "length", "stopped", "error"]),
    usage: z
      .object({ input_tokens: z.number(), output_tokens: z.number() })
      .optional(),
  }),
  z.object({
    type: z.literal("error"),
    code: z.string(),
    message: z.string(),
    conversation_id: id.optional(),
    client_id: id.optional(),
    retry_after: z.number().optional(),
  }),
  z.object({ type: z.literal("pong") }),
]);

export type ServerEvent = z.infer<typeof serverEventSchema>;

export type ClientCommand =
  | {
      type: "message.send";
      conversation_id: string;
      client_id: string;
      content: string;
      attachment_ids?: string[];
    }
  | { type: "generation.stop"; conversation_id: string }
  | { type: "ping" };

/** Turn raw socket data into a typed event, or null if it is not one we understand. */
export function parseServerEvent(raw: unknown): ServerEvent | null {
  if (typeof raw !== "string") return null;
  let data: unknown;
  try {
    data = JSON.parse(raw);
  } catch {
    return null;
  }
  const result = serverEventSchema.safeParse(data);
  return result.success ? result.data : null;
}

export function encodeCommand(command: ClientCommand): string {
  return JSON.stringify(command);
}
```

`parseServerEvent` returns a typed event or `null`. Callers simply ignore `null`: an unknown or malformed message is dropped, never trusted. Note that unknown extra fields are **removed** by the schema, so a stray `is_admin` field cannot sneak further into the app. The tests state those rules:

**text verified output**

```text
parses every event type the backend sends
accepts an empty delta (providers sometimes send one)
returns null for anything it does not understand
drops unknown extra fields instead of trusting them
produces JSON the backend can read
```


## A Reconnecting WebSocket Client › Backoff with jitter

If the delay after a failure were always the same, every client that lost the connection at the same moment (a server restart, say) would return at the same moment too, and knock the server over again. The fix has two parts: the waiting time **grows**, and each wait is a **random** value between zero and that limit. Real output of the ceiling for each attempt:

**text verified output**

```text
attempt 0: wait up to   500 ms
attempt 1: wait up to  1000 ms
attempt 2: wait up to  2000 ms
attempt 3: wait up to  4000 ms
attempt 4: wait up to  8000 ms
attempt 5: wait up to 16000 ms
attempt 6: wait up to 30000 ms
attempt 7: wait up to 30000 ms
```


## A Reconnecting WebSocket Client › How it was tested

Two kinds of test, because they catch different bugs. **Unit tests** drive the class with a fake WebSocket and a fake clock, so time is controlled exactly. A short excerpt:

**ts src/lib/realtime/socket.test.ts (excerpt)**

```typescript
it("waits longer after each failed attempt", async () => {
  const { socket, clock } = setup();
  socket.connect(); await flush();
  const waits: number[] = [];
  for (let i = 0; i < 4; i++) {
    last().serverCloses(1006); // never opened: counts as a failure
    const before = FakeSocket.all.length;
    let waited = 0;
    while (FakeSocket.all.length === before) { await clock.advance(1); waited++; }
    waits.push(waited);
  }
  expect(waits).toEqual([500, 1000, 2000, 4000]);
});

it("ignores late events from a socket it has already replaced", async () => {
  const { socket, clock, messages } = setup();
  socket.connect(); await flush(); last().serverOpens();
  const old = last();
  old.serverCloses(1006);
  await clock.advance(500); await flush(); last().serverOpens();
  old.serverSends("ghost"); // a delayed packet from the dead connection
  old.serverCloses(1006);   // and a duplicate close event
  expect(messages).toEqual([]);
  expect(socket.currentStatus).toBe("open");
});
```

**Integration tests** run the same class against a real server built with the `ws` library, over a real network connection. They are slower, but they found the bug a fake could not. Real output:

**text verified output**

```text
connects with a ticket and exchanges messages
reconnects with a fresh ticket after the server drops the connection
keeps retrying while the server is down and connects when it returns
stops for good when the server closes with a fatal code
stops when the ticket endpoint says the user is logged out
heartbeat pings reach the server and the pongs keep the link alive
detects a server that stops answering and reconnects
```

My first run of the integration tests failed on "keeps retrying while the server is down", and the cause was a real difference between runtimes (the refused-connection behaviour above), not a typo. That is the case for testing against the real thing at least once.


## Optimistic Updates › 2. Renaming or deleting a conversation (over REST)

For ordinary REST actions TanStack Query has a standard recipe with four steps:

1. `onMutate`**:** cancel in-flight refetches (they would overwrite your guess), save the current data, and write the new data into the cache. The UI changes instantly.
2. **The request** runs.
3. `onError`**:** put the saved data back. The user sees the change undone.
4. `onSettled`**:** refetch from the server, so the cache ends up matching the truth whether the request succeeded or failed.
**src/features/chat/conversations-cache.ts**

```
// Pure helpers for optimistic updates of the conversation list in the query cache.
export interface ConversationSummary {
  id: string;
  title: string;
}

export function renameInList<T extends ConversationSummary>(
  list: T[],
  id: string,
  title: string,
): T[] {
  return list.map((c) => (c.id === id ? { ...c, title } : c));
}

export function removeFromList<T extends ConversationSummary>(list: T[], id: string): T[] {
  return list.filter((c) => c.id !== id);
}
```

**src/features/chat/use-conversation-mutations.ts**

```
"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { deleteConversationApi, renameConversationApi } from "./api";
import { removeFromList, renameInList, type ConversationSummary } from "./conversations-cache";

const KEY = ["conversations"]; // the list query from Chapter 20

/**
 * The optimistic update recipe, in four steps:
 * 1. onMutate:  stop in-flight refetches (they would overwrite our guess), save the old
 *               data, and write the new data into the cache. The UI changes instantly.
 * 2. onError:   put the saved data back. The user sees the change undone.
 * 3. onSettled: refetch from the server, so the cache ends up matching the truth.
 */
function useOptimisticListMutation<TVars extends { id: string }>(
  mutationFn: (vars: TVars) => Promise<unknown>,
  apply: (list: ConversationSummary[], vars: TVars) => ConversationSummary[],
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn,
    onMutate: async (vars: TVars) => {
      await queryClient.cancelQueries({ queryKey: KEY });
      const previous = queryClient.getQueryData<ConversationSummary[]>(KEY);
      queryClient.setQueryData<ConversationSummary[]>(KEY, (old) =>
        old ? apply(old, vars) : old,
      );
      return { previous };
    },
    onError: (_error, _vars, context) => {
      if (context?.previous) queryClient.setQueryData(KEY, context.previous);
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: KEY }),
  });
}

export const useRenameConversation = () =>
  useOptimisticListMutation(
    ({ id, title }: { id: string; title: string }) => renameConversationApi(id, title),
    (list, { id, title }) => renameInList(list, id, title),
  );

export const useDeleteConversation = () =>
  useOptimisticListMutation(
    ({ id }: { id: string }) => deleteConversationApi(id),
    (list, { id }) => removeFromList(list, id),
  );
```

The cache edits are plain functions, so they are tested without TanStack Query: renaming changes only the target, leaves the other items as the same objects, and never mutates its input. Never mutate cached data in place; React and TanStack Query rely on "a new array means something changed".


## Loading States and Skeletons

A blank screen or a spinner tells users nothing. A **skeleton** is a grey outline with the rough shape of the content that is coming. It shows that the page is working, and because it takes the same space, nothing jumps when the real content arrives.

| **Use** | **When** |
|---|---|
| **Skeleton** | Content with a known shape: message lists, cards, tables |
| **Spinner** | A short action with no shape: saving, submitting |
| **Typing dots** | Waiting for the model to start answering |
| **Progress bar** | Anything with measurable progress: uploads |

**src/features/chat/components/skeletons.tsx**

```
import { Skeleton } from "@/components/ui/skeleton";

/** Same shape as the real list, so nothing jumps when messages arrive.
 *  No hooks, so it is safe in server components. */
export function MessageListSkeleton() {
  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6 px-4 py-6" aria-hidden="true">
      <div className="flex justify-end">
        <Skeleton className="h-10 w-2/5 rounded-2xl" />
      </div>
      <div className="space-y-2">
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-11/12" />
        <Skeleton className="h-4 w-3/5" />
      </div>
      <div className="flex justify-end">
        <Skeleton className="h-10 w-1/3 rounded-2xl" />
      </div>
      <div className="space-y-2">
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-4/5" />
      </div>
    </div>
  );
}
```

Next.js gives you the skeleton almost for free. A file named `loading.tsx` next to a `page.tsx` is shown instantly while the page loads (the App Router wraps the page in a Suspense boundary for you). The page itself is tiny, and note that in Next.js 16 `params` is a Promise that you `await`:

**tsx src/app/(app)/chat/[id]/page.tsx**

```tsx
import { ChatView } from "@/features/chat/components/chat-view";

// In Next.js 16 `params` is a Promise.
export default async function ChatPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ChatView conversationId={id} />;
}
```

**tsx src/app/(app)/chat/[id]/loading.tsx**

```tsx
import { MessageListSkeleton } from "@/features/chat/components/skeletons";

// Shown instantly while the route loads: same shape as the real page, so nothing jumps.
export default function Loading() {
  return (
    <div className="flex h-dvh flex-col">
      <div className="flex-1 overflow-hidden">
        <MessageListSkeleton />
      </div>
    </div>
  );
}
```

**tsx src/app/(app)/layout.tsx**

```tsx
import type { ReactNode } from "react";
import { ChatSocketProvider } from "@/features/chat/chat-socket-provider";

// Mounted in the layout, not in a page: the layout survives navigation between
// conversations, so there is ONE socket per browser tab for the whole signed-in area.
export default function AppLayout({ children }: { children: ReactNode }) {
  return <ChatSocketProvider>{children}</ChatSocketProvider>;
}
```

Two more rules for skeletons: hide them from assistive technology with `aria-hidden` (a screen reader should not read grey boxes), and give a **long wait** an honest message. The typing dots cover the first second or two; if the model is slow, the user still has the Stop button and the connection banner, and you can add a "this is taking longer than usual" note as an exercise.


## Code Blocks

A chat for developers lives or dies by its code blocks: syntax colours, a language label, horizontal scrolling for long lines, and a Copy button that works. Highlighting uses **Shiki**, which produces the same colours as VS Code. Two decisions keep it cheap:

- **Load it on demand.**  `await import("shiki")` runs only when a code block first appears, so Shiki never slows the first page load, and each language grammar loads only when used.
- **Highlight after the text stops changing.** A streaming block would otherwise be highlighted on every frame. A 150 ms pause in the effect means a streaming block is highlighted once it settles, and any stale result is discarded.
**src/features/chat/highlight.ts**

```
/** Syntax highlighting with Shiki, loaded on demand so it never slows the first page load. */
export async function highlight(code: string, language: string | undefined): Promise<string> {
  const { codeToHtml, bundledLanguages } = await import("shiki");
  const lang = language && language in bundledLanguages ? language : "text";
  return codeToHtml(code, {
    lang,
    themes: { light: "github-light", dark: "github-dark" },
    defaultColor: false, // emit CSS variables, so light/dark switching needs no re-render
  });
}
```

With `defaultColor: false` Shiki writes **CSS variables** instead of fixed colours, one set per theme. Dark mode then needs no re-render: a few lines of CSS pick the right variables, using the `dark` class from Chapter 19. Add this to `globals.css`:

**css src/app/globals.css (additions)**

```css
.shiki {
  background-color: var(--shiki-light-bg);
}
.shiki span {
  color: var(--shiki-light);
}
.dark .shiki {
  background-color: var(--shiki-dark-bg);
}
.dark .shiki span {
  color: var(--shiki-dark);
}
```

**src/features/chat/components/code-block.tsx**

```
"use client";

import { useEffect, useState } from "react";
import { highlight } from "../highlight";

export function CodeBlock({ code, language }: { code: string; language?: string }) {
  const [html, setHtml] = useState<string | null>(null);
  const [copy, setCopy] = useState<"idle" | "copied" | "failed">("idle");

  // Highlight shortly after the text stops changing, so a streaming block is not
  // re-highlighted on every frame. A stale result is discarded.
  useEffect(() => {
    let cancelled = false;
    const timer = setTimeout(() => {
      highlight(code, language)
        .then((result) => !cancelled && setHtml(result))
        .catch(() => undefined); // on failure we simply keep the plain text
    }, 150);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [code, language]);

  useEffect(() => {
    if (copy === "idle") return;
    const timer = setTimeout(() => setCopy("idle"), 2000);
    return () => clearTimeout(timer);
  }, [copy]);

  async function copyCode() {
    try {
      await navigator.clipboard.writeText(code); // needs https or localhost
      setCopy("copied");
    } catch {
      setCopy("failed");
    }
  }

  return (
    <div className="my-3 overflow-hidden rounded-lg border bg-muted/40">
      <div className="flex items-center justify-between border-b px-3 py-1.5 text-xs">
        <span className="font-mono text-muted-foreground">{language ?? "text"}</span>
        <button
          type="button"
          onClick={copyCode}
          className="rounded px-2 py-0.5 hover:bg-muted focus-visible:ring-2"
        >
          {copy === "copied" ? "Copied" : copy === "failed" ? "Copy failed" : "Copy"}
          <span className="sr-only"> code</span>
        </button>
      </div>
      {html ? (
        // Safe: Shiki HTML-escapes the code it highlights. We never pass it model text as HTML.
        <div
          className="overflow-x-auto p-3 text-sm [&_pre]:bg-transparent!"
          dangerouslySetInnerHTML={{ __html: html }}
        />
      ) : (
        <pre className="overflow-x-auto p-3 text-sm">
          <code>{code}</code>
        </pre>
      )}
    </div>
  );
}
```

Three details: the Copy button uses `navigator.clipboard.writeText`, which works only in a secure context and can be refused, so it shows "Copy failed" instead of pretending; the label has a visually hidden "code" so a screen reader hears "Copy code"; and the one use of `dangerouslySetInnerHTML` in the chapter is justified in a comment, because Shiki **escapes** the code it highlights. That is a very different thing from inserting model text as HTML, which we never do.


## File Uploads › Progress, errors and cancellation

`fetch` cannot report **upload** progress, so uploads use `XMLHttpRequest`, which fires progress events. Two rules in the code are worth highlighting: it never sets a `Content-Type` header itself (the browser must add the multipart boundary, and setting it by hand breaks the upload), and it turns the usual error shapes (`{"detail": ...}` from DRF, `{"error": {"message": ...}}`) into a readable sentence. The XHR object is a parameter, so the logic is tested with a fake: progress, success, 400 and 413 errors, a network error and cancellation with an `AbortSignal`.

**src/features/chat/attachments.ts**

```
// Client-side checks are for the USER's benefit (fast feedback). They are not security:
// the server must repeat every check (Chapter 17), because anyone can bypass this code.

export interface FileRules {
  maxBytes: number;
  maxFiles: number;
  types: string[]; // MIME types the browser reports (a hint, easily wrong or empty)
  extensions: string[]; // lower-case, without the dot
}

export const DEFAULT_RULES: FileRules = {
  maxBytes: 10 * 1024 * 1024,
  maxFiles: 5,
  types: [
    "image/png", "image/jpeg", "image/webp", "image/gif",
    "application/pdf", "text/plain", "text/markdown",
  ],
  extensions: ["png", "jpg", "jpeg", "webp", "gif", "pdf", "txt", "md"],
};

export interface FileLike {
  name: string;
  size: number;
  type: string;
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1).replace(/\.0$/, "")} MB`;
}

/** Returns a message for the user, or null when the file is acceptable. */
export function validateFile(file: FileLike, rules: FileRules = DEFAULT_RULES): string | null {
  const dot = file.name.lastIndexOf(".");
  const extension = dot >= 0 ? file.name.slice(dot + 1).toLowerCase() : "";
  if (!rules.extensions.includes(extension)) return "This file type is not supported.";
  if (file.type !== "" && !rules.types.includes(file.type)) {
    return "This file type is not supported.";
  }
  if (file.size === 0) return "This file is empty.";
  if (file.size > rules.maxBytes) {
    return `This file is larger than ${formatBytes(rules.maxBytes)}.`;
  }
  return null;
}

export function validateBatch<T extends FileLike>(
  alreadyAttached: number,
  files: T[],
  rules: FileRules = DEFAULT_RULES,
): { accepted: T[]; rejected: { name: string; reason: string }[] } {
  const accepted: T[] = [];
  const rejected: { name: string; reason: string }[] = [];
  for (const file of files) {
    const problem = validateFile(file, rules);
    if (problem) rejected.push({ name: file.name, reason: problem });
    else if (alreadyAttached + accepted.length >= rules.maxFiles) {
      const reason = `You can attach up to ${rules.maxFiles} files.`;
      rejected.push({ name: file.name, reason });
    } else accepted.push(file);
  }
  return { accepted, rejected };
}

// ------------------------------------------------------------------ state

export interface Attachment {
  localId: string;
  name: string;
  size: number;
  type: string;
  status: "uploading" | "done" | "error";
  progress: number; // 0 to 100
  uploadId?: string; // the server's id, once uploaded
  error?: string;
  previewUrl?: string; // an object URL for images: revoke it when the item is removed
}

export type AttachmentAction =
  | { type: "add"; item: Pick<Attachment, "localId" | "name" | "size" | "type" | "previewUrl"> }
  | { type: "progress"; localId: string; progress: number }
  | { type: "done"; localId: string; uploadId: string }
  | { type: "fail"; localId: string; error: string }
  | { type: "retry"; localId: string }
  | { type: "remove"; localId: string }
  | { type: "clear" };

export function attachmentsReducer(
  state: Attachment[],
  action: AttachmentAction,
): Attachment[] {
  const change = (id: string, patch: Partial<Attachment>) =>
    state.map((a) => (a.localId === id ? { ...a, ...patch } : a));
  switch (action.type) {
    case "add":
      return [...state, { ...action.item, status: "uploading", progress: 0 }];
    case "progress":
      return change(action.localId, { progress: Math.max(0, Math.min(100, action.progress)) });
    case "done":
      return change(action.localId, {
        status: "done", progress: 100, uploadId: action.uploadId, error: undefined,
      });
    case "fail":
      return change(action.localId, { status: "error", error: action.error });
    case "retry":
      return change(action.localId, { status: "uploading", progress: 0, error: undefined });
    case "remove":
      return state.filter((a) => a.localId !== action.localId);
    case "clear":
      return [];
  }
}

export const uploadedIds = (items: Attachment[]): string[] =>
  items.flatMap((a) => (a.status === "done" && a.uploadId ? [a.uploadId] : []));

/** The message may be sent only when nothing is still uploading or failed. */
export const attachmentsReady = (items: Attachment[]): boolean =>
  items.every((a) => a.status === "done");

// ------------------------------------------------------------------ upload

export class UploadError extends Error {
  constructor(message: string, readonly status = 0, readonly cancelled = false) {
    super(message);
  }
}

interface ProgressLike {
  lengthComputable: boolean;
  loaded: number;
  total: number;
}

/** The part of XMLHttpRequest we use. Tests supply a fake. */
export interface XhrLike {
  open(method: string, url: string): void;
  setRequestHeader(name: string, value: string): void;
  send(body: FormData): void;
  abort(): void;
  withCredentials: boolean;
  status: number;
  responseText: string;
  upload: { onprogress: ((e: ProgressLike) => void) | null };
  onload: (() => void) | null;
  onerror: (() => void) | null;
  onabort: (() => void) | null;
}

export interface UploadOptions {
  url: string;
  headers?: Record<string, string>; // for example Authorization (never Content-Type)
  withCredentials?: boolean; // true when authentication uses cookies
  onProgress?: (percent: number) => void;
  signal?: AbortSignal;
}

/** Pull a readable message out of the usual error shapes (DRF "detail", {error:{message}}). */
export function messageFromResponse(text: string): string | null {
  try {
    const body = JSON.parse(text) as {
      error?: { message?: unknown };
      detail?: unknown;
      message?: unknown;
    };
    for (const candidate of [body.error?.message, body.detail, body.message]) {
      if (typeof candidate === "string" && candidate) return candidate;
    }
  } catch {
    /* not JSON */
  }
  return null;
}

/** fetch() cannot report upload progress, so uploads use XMLHttpRequest. */
export function uploadFile(
  file: Blob & { name: string },
  options: UploadOptions,
  createXhr: () => XhrLike = () => new XMLHttpRequest() as unknown as XhrLike,
): Promise<{ id: string }> {
  return new Promise((resolve, reject) => {
    const xhr = createXhr();
    xhr.open("POST", options.url);
    xhr.withCredentials = options.withCredentials ?? false;
    for (const [name, value] of Object.entries(options.headers ?? {})) {
      xhr.setRequestHeader(name, value);
    }

    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) options.onProgress?.(Math.round((e.loaded / e.total) * 100));
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          const body = JSON.parse(xhr.responseText) as { id?: unknown };
          if (typeof body.id === "string" && body.id) return resolve({ id: body.id });
        } catch {
          /* fall through */
        }
        return reject(new UploadError("The server sent an unexpected response.", xhr.status));
      }
      const fallback =
        xhr.status === 413 ? "The file is too large." : `Upload failed (${xhr.status}).`;
      reject(new UploadError(messageFromResponse(xhr.responseText) ?? fallback, xhr.status));
    };
    xhr.onerror = () =>
      reject(new UploadError("Network error. Check your connection and try again."));
    xhr.onabort = () => reject(new UploadError("Upload cancelled.", 0, true));

    if (options.signal) {
      if (options.signal.aborted) return reject(new UploadError("Upload cancelled.", 0, true));
      options.signal.addEventListener("abort", () => xhr.abort(), { once: true });
    }
    const form = new FormData();
    // no Content-Type header: the browser adds the multipart boundary itself
    form.append("file", file, file.name);
    xhr.send(form);
  });
}
```

The tray shows each file as a chip: a thumbnail for images (made with `URL.createObjectURL`), a native `<progress>` element with an accessible label, the error with a Retry button, and a Remove button. The composer, shown earlier, handles drag, drop and paste. Two memory details are easy to miss:

- **Revoke object URLs.** Every `URL.createObjectURL` holds the file in memory until you call `URL.revokeObjectURL`. The composer revokes on remove, on send and on unmount.
- **Reset the file input.** After choosing files, `e.target.value = ""` lets the user choose the **same** file again; otherwise the browser sees no change and fires no event.
For very large files, a later optimisation is to upload straight to object storage with a pre-signed URL (Chapter 16) instead of through Django. The shape of the code, with an `uploadFile` that reports progress, stays the same.
