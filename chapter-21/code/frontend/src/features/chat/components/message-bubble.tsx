"use client";

import { memo } from "react";
import type { ChatMessage, FinishReason } from "../chat-state";
import { Markdown } from "./markdown";
import { TypingIndicator } from "./small-ui";

const FINISH_NOTES: Partial<Record<FinishReason, string>> = {
  length: "This reply was cut off because it reached the length limit.",
  stopped: "You stopped this reply.",
  interrupted:
    "The connection dropped while this was being written. Reload to see what was saved.",
  error: "Something went wrong while writing this reply.",
};

interface Props {
  message: ChatMessage;
  onRetry: (clientId: string) => void;
}

// memo: the reducer keeps unchanged messages as the same objects, so only the
// message that is streaming re-renders when a token arrives.
export const MessageBubble = memo(function MessageBubble({ message, onRetry }: Props) {
  if (message.role === "user") {
    const failed = message.status === "failed";
    const files = message.attachmentIds?.length ?? 0;
    const bubble =
      "max-w-[85%] whitespace-pre-wrap break-words rounded-2xl bg-primary " +
      "px-4 py-2 text-primary-foreground";
    return (
      <div className="flex flex-col items-end gap-1">
        <div className={message.status === "sending" ? `${bubble} opacity-70` : bubble}>
          {message.content}
        </div>
        {files > 0 && (
          <span className="text-xs text-muted-foreground">
            {files} attached file{files > 1 ? "s" : ""}
          </span>
        )}
        {message.status === "sending" && (
          <span className="text-xs text-muted-foreground">Sending...</span>
        )}
        {failed && (
          <span role="alert" className="text-xs text-destructive">
            {message.error ?? "Not sent."}{" "}
            <button
              type="button"
              className="font-medium underline"
              onClick={() => onRetry(message.clientId ?? message.id)}
            >
              Retry
            </button>
          </span>
        )}
      </div>
    );
  }

  const note = message.finishReason ? FINISH_NOTES[message.finishReason] : undefined;
  return (
    <div aria-busy={message.streaming === true}>
      {message.streaming && message.content === "" ? (
        <TypingIndicator />
      ) : (
        <Markdown text={message.content} streaming={message.streaming === true} />
      )}
      {message.streaming && message.content !== "" && (
        <span
          aria-hidden="true"
          className="ml-0.5 inline-block h-4 w-1.5 bg-current motion-safe:animate-pulse"
        />
      )}
      {note && <p className="mt-2 text-sm text-muted-foreground">{note}</p>}
    </div>
  );
});
