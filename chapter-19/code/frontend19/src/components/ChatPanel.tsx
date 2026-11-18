"use client";

import { SendHorizontal } from "lucide-react";
import {
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
} from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
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
      setMessages((current) => [
        ...current.filter((m) => m.id !== optimistic.id),
        userMessage,
        assistantMessage,
      ]);
    } catch {
      setMessages((current) => current.filter((m) => m.id !== optimistic.id));
      setDraft(content);
      setError("Your message was not sent. Please try again.");
    } finally {
      setSending(false);
    }
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      event.currentTarget.form?.requestSubmit();
    }
  }

  return (
    <section className="flex h-full flex-col" aria-label="Conversation">
      <div className="flex-1 overflow-y-auto p-4">
        <MessageList messages={messages} />
        {sending && (
          <p className="text-muted-foreground mt-3 text-sm" role="status">
            The assistant is typing…
          </p>
        )}
        <div ref={bottomRef} />
      </div>

      <form onSubmit={handleSubmit} className="border-t p-4">
        {error && (
          <p role="alert" className="text-destructive mb-2 text-sm">
            {error}
          </p>
        )}
        <div className="flex items-end gap-2">
          <Textarea
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Write a message…"
            aria-label="Message"
            rows={2}
          />
          <Button
            type="submit"
            size="icon"
            disabled={sending || draft.trim() === ""}
          >
            <SendHorizontal aria-hidden="true" />
            <span className="sr-only">Send</span>
          </Button>
        </div>
      </form>
    </section>
  );
}
