"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { useChat, type UseChatOptions } from "../shared/use-chat";

export default function ChatPane(props: UseChatOptions) {
  const { state, send, stop, clearError } = useChat(props);
  const [draft, setDraft] = useState("");
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => { bottom.current?.scrollIntoView({ behavior: "smooth" }); }, [state.messages]);

  const submit = () => { if (send(draft)) setDraft(""); };
  const canSend = state.connection === "open" && !state.busy && !state.limitReached && draft.trim().length > 0;

  return (
    <section className="flex h-full flex-col">
      <header className="flex items-center justify-between border-b px-4 py-2 text-sm">
        <span>{state.plan?.name ?? "…"} plan</span>
        <span>{state.usage ? `${state.usage.used}/${state.usage.limit} messages today` : ""}</span>
        <span aria-live="polite">{state.connection === "open" ? "Online" : "Reconnecting…"}</span>
      </header>

      <ol className="flex-1 space-y-3 overflow-y-auto p-4">
        {state.messages.map((m) => (
          // Render model output as TEXT. Never dangerouslySetInnerHTML (Chapter 17). Chapter 21 adds safe Markdown.
          <li key={m.key} className={m.role === "user" ? "ml-auto max-w-[80%] rounded-lg bg-blue-600 p-3 text-white"
                                                       : "mr-auto max-w-[80%] whitespace-pre-wrap rounded-lg bg-gray-100 p-3"}>
            {m.content || (m.status === "streaming" ? "…" : "")}
            {m.status === "stopped" && <em className="block text-xs opacity-70">Stopped</em>}
            {m.status === "error" && <em className="block text-xs text-red-600">This answer did not finish.</em>}
          </li>
        ))}
        <div ref={bottom} />
      </ol>

      {state.error && (
        <div role="alert" className="flex items-center justify-between bg-amber-50 px-4 py-2 text-sm">
          <span>{state.error.message}</span>
          {state.limitReached && <Link href="/billing" className="font-semibold underline">Upgrade</Link>}
          <button onClick={clearError} className="ml-2" aria-label="Dismiss">×</button>
        </div>
      )}

      <form className="flex gap-2 border-t p-3" onSubmit={(e) => { e.preventDefault(); if (canSend) submit(); }}>
        <textarea value={draft} onChange={(e) => setDraft(e.target.value)} rows={2} maxLength={8000}
                  className="flex-1 resize-none rounded border p-2" placeholder="Ask anything…"
                  onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); if (canSend) submit(); } }} />
        {state.busy
          ? <button type="button" onClick={stop} className="rounded bg-gray-800 px-4 text-white">Stop</button>
          : <button type="submit" disabled={!canSend} className="rounded bg-blue-600 px-4 text-white disabled:opacity-50">Send</button>}
      </form>
    </section>
  );
}
