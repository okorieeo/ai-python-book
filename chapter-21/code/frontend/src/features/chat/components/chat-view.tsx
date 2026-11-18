"use client";

import { useChatController } from "../use-chat-controller";
import { Composer } from "./composer";
import { MessageList } from "./message-list";
import { ConnectionBanner, ErrorNotice } from "./small-ui";

export function ChatView({ conversationId }: { conversationId: string }) {
  const chat = useChatController(conversationId);

  return (
    <div className="flex h-dvh flex-col">
      <ConnectionBanner status={chat.connection} onRetry={chat.reconnectNow} />
      {chat.historyError ? (
        <div role="alert" className="grid flex-1 place-items-center p-6 text-center">
          <div>
            <p className="mb-3">We could not load this conversation.</p>
            <button
              type="button"
              className="underline"
              onClick={() => void chat.refetchHistory()}
            >
              Try again
            </button>
          </div>
        </div>
      ) : (
        <MessageList
          messages={chat.messages}
          loading={chat.loadingHistory}
          awaitingReply={chat.awaitingReply}
          generating={chat.generating}
          onRetry={chat.retry}
        />
      )}
      {chat.error && <ErrorNotice error={chat.error} onDismiss={chat.dismissError} />}
      <Composer
        connected={chat.connection === "open"}
        generating={chat.generating}
        onSend={chat.send}
        onStop={chat.stop}
      />
    </div>
  );
}
