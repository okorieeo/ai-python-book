"use client";

import { messageForError } from "@/lib/api/errors";
import { flattenPages } from "@/lib/query/cache-updates";
import { useConversations } from "@/lib/query/hooks";

export function ConversationList() {
  const query = useConversations(20);

  if (query.isPending) return <p aria-busy="true">Loading your conversations...</p>;

  if (query.isError) {
    return (
      <div role="alert">
        <p>{messageForError(query.error)}</p>
        <button onClick={() => query.refetch()}>Try again</button>
      </div>
    );
  }

  const conversations = flattenPages(query.data);
  if (conversations.length === 0) {
    return <p>No conversations yet. Create one above, for example: &ldquo;Draft a polite reply to a customer&rdquo;.</p>;
  }

  return (
    <>
      <ul>
        {conversations.map((conversation) => (
          <li key={conversation.id}>
            {conversation.title}{" "}
            <time dateTime={conversation.created_at}>{new Date(conversation.created_at).toLocaleDateString()}</time>
          </li>
        ))}
      </ul>
      {query.hasNextPage ? (
        <button onClick={() => query.fetchNextPage()} disabled={query.isFetchingNextPage} aria-busy={query.isFetchingNextPage}>
          {query.isFetchingNextPage ? "Loading..." : "Load more"}
        </button>
      ) : null}
    </>
  );
}
