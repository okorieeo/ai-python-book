"use client";

import {
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
} from "react";
import { useLocalStorage } from "@/hooks/useLocalStorage";
import type { Message } from "@/lib/types";
import { MessageList } from "./MessageList";

interface ChatPanelProps {
  conversationId: string;
  initialMessages: Message[];
}

export function ChatPanel({ conversationId, initialMessages }: ChatPanelProps) {
  const [messages, setMessages] = useState<Message[]>(initialMessages);
  const [draft, setDraft] = useLocalStorage(`draft:${conversationId}`, "");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  // After every change to the list, scroll the newest message into view.
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end" });
  }, [messages]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const content = draft.trim();
    if (!content || sending) return;

    setError(null);
    setSending(true);
    setDraft("");
    // Optimistic update: show the message at once, with a temporary negative id.
    const optimistic: Message = {
      id: -Date.now(),
      role: "user",
      content,
      createdAt: new Date().toISOString(),
    };
    setMessages((current) => [...current, optimistic]);

    try {
      const response = await fetch(
        `/api/conversations/${conversationId}/messages`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ content }),
        },
      );
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const { userMessage, assistantMessage } = (await response.json()) as {
        userMessage: Message;
        assistantMessage: Message;
      };
      // Replace the temporary message with the real one, then add the answer.
      setMessages((current) => [
        ...current.filter((m) => m.id !== optimistic.id),
        userMessage,
        assistantMessage,
      ]);
    } catch {
      // Undo the optimistic update and give the user their text back.
      setMessages((current) => current.filter((m) => m.id !== optimistic.id));
      setDraft(content);
      setError("Your message was not sent. Please try again.");
    } finally {
      setSending(false);
    }
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault(); // Enter sends; Shift+Enter adds a new line
      event.currentTarget.form?.requestSubmit();
    }
  }

  return (
    <section className="flex h-full flex-col">
      <div className="flex-1 overflow-y-auto p-4">
        <MessageList messages={messages} />
        {sending && (
          <p className="mt-3 text-sm text-zinc-500" role="status">
            The assistant is typing…
          </p>
        )}
        <div ref={bottomRef} />
      </div>

      <form onSubmit={handleSubmit} className="border-t p-4">
        {error && (
          <p role="alert" className="mb-2 text-sm text-red-600">
            {error}
          </p>
        )}
        <div className="flex gap-2">
          <textarea
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Write a message…"
            aria-label="Message"
            rows={2}
            className="flex-1 resize-none rounded-lg border p-2 text-sm"
          />
          <button
            type="submit"
            disabled={sending || draft.trim() === ""}
            className="rounded-lg bg-blue-600 px-4 text-sm font-medium text-white disabled:opacity-50"
          >
            Send
          </button>
        </div>
      </form>
    </section>
  );
}
