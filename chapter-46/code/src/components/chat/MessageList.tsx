"use client";

import { useEffect, useRef } from "react";
import dynamic from "next/dynamic";
import type { ChatMessage } from "@/lib/chat/reducer";
import { cn } from "@/lib/utils";

// The markdown renderer is the heaviest part of the chat bundle, and it is not needed
// until the first assistant message exists, so it loads on demand (46.7).
const Markdown = dynamic(() => import("./Markdown"), {
  loading: () => <span className="text-muted-foreground">…</span>,
});

export function MessageList({ messages, busy }: { messages: ChatMessage[]; busy: boolean }) {
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
        // If the reader scrolled up, stop pulling them back down while tokens arrive.
        stickToBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 48;
      }}
      className="flex-1 overflow-y-auto p-4"
    >
      <ul className="mx-auto flex max-w-3xl flex-col gap-4">
        {messages.map((message) => (
          <li
            key={message.id}
            className={cn(
              "max-w-[85%] rounded-md px-4 py-2 text-sm leading-6",
              message.role === "user" ? "self-end bg-primary text-primary-foreground" : "self-start bg-muted",
            )}
          >
            <span className="sr-only">{message.role === "user" ? "You said:" : "Assistant said:"}</span>
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
