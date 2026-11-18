import { listConversations } from "@/lib/data";
import { Skeleton } from "@/components/ui/skeleton";
import { ConversationLink } from "./ConversationLink";

// An async Server Component: it fetches its own data, and ships no JavaScript.
export async function Sidebar() {
  const conversations = await listConversations();
  if (conversations.length === 0) {
    return (
      <p className="text-muted-foreground px-3 text-sm">
        No conversations yet.
      </p>
    );
  }
  return (
    <nav aria-label="Conversations" className="flex flex-col gap-1">
      {conversations.map((conversation) => (
        <ConversationLink
          key={conversation.id}
          id={conversation.id}
          title={conversation.title}
        />
      ))}
    </nav>
  );
}

export function SidebarSkeleton() {
  return (
    <div className="flex flex-col gap-2 px-3">
      {[0, 1, 2].map((i) => (
        <Skeleton key={i} className="h-8" />
      ))}
    </div>
  );
}
