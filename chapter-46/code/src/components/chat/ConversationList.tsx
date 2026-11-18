import Link from "next/link";
import { cn } from "@/lib/utils";

export type ConversationSummary = { public_id: string; title: string; updated_at: string };

type Props = { conversations: ConversationSummary[]; activeId?: string };

export function ConversationList({ conversations, activeId }: Props) {
  if (conversations.length === 0) {
    return <p className="p-4 text-sm text-muted-foreground">No conversations yet. Start one below.</p>;
  }
  return (
    <nav aria-label="Conversations">
      <ul className="flex flex-col gap-1 p-2">
        {conversations.map((conversation) => {
          const active = conversation.public_id === activeId;
          return (
            <li key={conversation.public_id}>
              <Link
                href={`/chat/${conversation.public_id}`}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "block truncate rounded-md px-3 py-2 text-sm hover:bg-muted",
                  "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
                  active && "bg-muted font-medium",
                )}
              >
                {conversation.title || "Untitled"}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
