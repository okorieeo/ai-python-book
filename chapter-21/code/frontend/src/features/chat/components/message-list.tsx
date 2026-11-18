"use client";

import { useEffect, useRef, useState } from "react";
import type { ChatMessage } from "../chat-state";
import { useStickToBottom } from "../use-stick-to-bottom";
import { MessageBubble } from "./message-bubble";
import { MessageListSkeleton } from "./skeletons";
import { TypingIndicator } from "./small-ui";

interface Props {
  messages: ChatMessage[];
  loading: boolean;
  awaitingReply: boolean;
  generating: boolean;
  onRetry: (clientId: string) => void;
}

export function MessageList({ messages, loading, awaitingReply, generating, onRetry }: Props) {
  const { scrollRef, contentRef, onScroll, showJump, scrollToBottom } = useStickToBottom();

  // Screen readers should hear "writing" and "finished", not every single token.
  const [announcement, setAnnouncement] = useState("");
  const wasGenerating = useRef(false);
  useEffect(() => {
    if (generating && !wasGenerating.current) {
      setAnnouncement("The assistant is writing a reply.");
    }
    if (!generating && wasGenerating.current) setAnnouncement("The reply is finished.");
    wasGenerating.current = generating;
  }, [generating]);

  // When the user sends something, jump to it even if they had scrolled up.
  const lastUserId = [...messages].reverse().find((m) => m.role === "user")?.id;
  useEffect(() => {
    if (lastUserId) scrollToBottom();
  }, [lastUserId, scrollToBottom]);

  if (loading) return <MessageListSkeleton />;

  return (
    <div className="relative min-h-0 flex-1">
      <div
        ref={scrollRef}
        onScroll={onScroll}
        role="log"
        aria-label="Conversation"
        aria-live="off"
        aria-busy={generating}
        className="h-full overflow-y-auto px-4"
      >
        <div ref={contentRef} className="mx-auto flex max-w-3xl flex-col gap-6 py-6">
          {messages.length === 0 && (
            <p className="py-16 text-center text-muted-foreground">Send a message to start.</p>
          )}
          {messages.map((m) => (
            <MessageBubble key={m.clientId ?? m.id} message={m} onRetry={onRetry} />
          ))}
          {awaitingReply && <TypingIndicator />}
        </div>
      </div>
      {showJump && (
        <button
          type="button"
          onClick={() => scrollToBottom(true)}
          className={
            "absolute bottom-4 left-1/2 -translate-x-1/2 rounded-full border " +
            "bg-background px-4 py-1.5 text-sm shadow"
          }
        >
          Jump to latest
        </button>
      )}
      <div role="status" className="sr-only">
        {announcement}
      </div>
    </div>
  );
}
