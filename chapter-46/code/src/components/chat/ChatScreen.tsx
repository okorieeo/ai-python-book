"use client";

import { useCallback } from "react";
import { fetchSocketUrl, useConversations, useMessages } from "@/lib/api/queries";
import { friendlyMessage } from "@/lib/api/errors";
import { ChatWindow } from "./ChatWindow";
import { ConversationList } from "./ConversationList";

export function ChatScreen({ conversationId }: { conversationId?: string }) {
  const conversations = useConversations();

  return (
    <div className="flex h-dvh flex-col md:flex-row">
      <aside className="max-h-40 overflow-y-auto border-b border-border md:max-h-none md:w-72 md:border-r md:border-b-0">
        {conversations.isPending && <p className="p-4 text-sm text-muted-foreground">Loading…</p>}
        {conversations.isError && (
          <p role="alert" className="p-4 text-sm text-danger">
            {friendlyMessage(conversations.error)}
          </p>
        )}
        {conversations.data && (
          <ConversationList conversations={conversations.data.results} activeId={conversationId} />
        )}
      </aside>
      <main className="min-h-0 flex-1">
        {conversationId ? (
          <ActiveChat key={conversationId} conversationId={conversationId} />
        ) : (
          <p className="p-6 text-muted-foreground">Choose a conversation to begin.</p>
        )}
      </main>
    </div>
  );
}

function ActiveChat({ conversationId }: { conversationId: string }) {
  const history = useMessages(conversationId);
  const resolveUrl = useCallback(() => fetchSocketUrl(conversationId), [conversationId]);

  if (history.isPending) return <p className="p-6 text-muted-foreground">Loading messages…</p>;
  if (history.isError) {
    return (
      <p role="alert" className="p-6 text-danger">
        {friendlyMessage(history.error)}
      </p>
    );
  }
  // `key` on ActiveChat resets the chat state when the conversation changes.
  return <ChatWindow resolveUrl={resolveUrl} initialMessages={history.data} />;
}
