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

// Messages for the codes the server can send. Anything else gets the generic sentence.
const ERROR_TEXT: Record<string, string> = {
  rate_limited: "You are sending messages too quickly. Wait a moment and try again.",
  budget_exceeded: "You have reached today's AI usage limit. It resets tomorrow.",
  connection_lost: "The connection dropped before the reply finished. You can send your message again.",
};

export function ChatWindow({ resolveUrl, initialMessages, socketFactory }: Props) {
  const { state, connection, send } = useChatStream({ resolveUrl, initialMessages, socketFactory });
  const streaming = state.status === "streaming";

  return (
    <section aria-label="Chat" className="flex h-full min-h-0 flex-col">
      {connection !== "open" && (
        <p role="status" className="bg-muted px-4 py-2 text-sm text-muted-foreground">
          {connection === "connecting" ? "Connecting…" : "Connection lost. Reconnecting…"}
        </p>
      )}
      <MessageList messages={state.messages} busy={streaming} />
      {state.error && (
        <p role="alert" className="px-4 py-2 text-sm text-danger">
          {ERROR_TEXT[state.error.code] ?? "Something went wrong. Please try again."}
        </p>
      )}
      <Composer onSend={send} disabled={connection !== "open" || streaming} />
    </section>
  );
}
