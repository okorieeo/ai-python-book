import { ChatView } from "@/features/chat/components/chat-view";

// In Next.js 16 `params` is a Promise.
export default async function ChatPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ChatView conversationId={id} />;
}
