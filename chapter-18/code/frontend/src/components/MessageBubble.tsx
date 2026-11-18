import type { Message } from "@/lib/types";

interface MessageBubbleProps {
  message: Pick<Message, "role" | "content">;
  pending?: boolean;
}

export function MessageBubble({
  message,
  pending = false,
}: MessageBubbleProps) {
  const isUser = message.role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={[
          "max-w-[80%] whitespace-pre-wrap rounded-2xl px-4 py-2 text-sm",
          isUser ? "bg-blue-600 text-white" : "bg-zinc-100 text-zinc-900",
          pending ? "opacity-60" : "",
        ].join(" ")}
        data-role={message.role}
      >
        {message.content}
      </div>
    </div>
  );
}
