import type { Message } from "@/lib/types";
import { MessageBubble } from "./MessageBubble";

export function MessageList({ messages }: { messages: Message[] }) {
  if (messages.length === 0) {
    return (
      <p className="m-auto text-sm text-zinc-500">
        No messages yet. Say hello!
      </p>
    );
  }
  return (
    <ul className="flex flex-col gap-3" aria-label="Messages">
      {messages.map((message) => (
        <li key={message.id}>
          <MessageBubble message={message} pending={message.id < 0} />
        </li>
      ))}
    </ul>
  );
}
