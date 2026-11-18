import { listConversations } from "@/lib/data";
import { ConversationLink } from "./ConversationLink";

// An async Server Component: it fetches its own data, and ships no JavaScript.
export async function Sidebar() {
  const conversations = await listConversations();
  if (conversations.length === 0) {
    return <p className="px-3 text-sm text-zinc-500">No conversations yet.</p>;
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
    <div className="flex flex-col gap-2 px-3" aria-hidden="true">
      {[0, 1, 2].map((i) => (
        <div key={i} className="h-8 animate-pulse rounded-md bg-zinc-100" />
      ))}
    </div>
  );
}
