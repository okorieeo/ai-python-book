import { notFound } from "next/navigation";
import { ChatPanel } from "@/components/ChatPanel";
import { getConversation } from "@/lib/data";

export default async function ConversationPage(props: PageProps<"/chat/[id]">) {
  const { id } = await props.params; // params is a Promise in current Next.js
  const conversation = await getConversation(id);
  if (!conversation) notFound(); // renders not-found.tsx with a 404 status

  // `key` makes React start a fresh ChatPanel (with fresh state) for each conversation.
  return (
    <ChatPanel
      key={conversation.id}
      conversationId={conversation.id}
      initialMessages={conversation.messages}
    />
  );
}
