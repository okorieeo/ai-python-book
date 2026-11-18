import { cn } from "@/lib/utils";
import type { Message } from "@/lib/types";
import { LocalTime } from "./LocalTime";

interface MessageBubbleProps {
  message: Pick<Message, "role" | "content"> & { createdAt?: string };
  pending?: boolean;
}

export function MessageBubble({
  message,
  pending = false,
}: MessageBubbleProps) {
  const isUser = message.role === "user";
  return (
    <div className={cn("flex", isUser ? "justify-end" : "justify-start")}>
      <div
        data-role={message.role}
        className={cn(
          "max-w-[85%] rounded-2xl px-4 py-2 text-sm whitespace-pre-wrap sm:max-w-[75%]",
          isUser
            ? "bg-primary text-primary-foreground"
            : "bg-muted text-foreground",
          pending && "opacity-60",
        )}
      >
        <p>{message.content}</p>
        {message.createdAt && !pending && (
          <LocalTime
            iso={message.createdAt}
            className="mt-1 block text-xs opacity-80"
          />
        )}
      </div>
    </div>
  );
}
