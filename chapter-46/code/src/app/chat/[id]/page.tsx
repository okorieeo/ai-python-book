import { ChatScreen } from "@/components/chat/ChatScreen";

// In Next.js 15 and later, `params` is a Promise and must be awaited.
export default async function ConversationPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ChatScreen conversationId={id} />;
}
