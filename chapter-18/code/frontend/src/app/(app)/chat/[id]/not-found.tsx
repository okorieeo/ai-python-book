import Link from "next/link";

export default function ConversationNotFound() {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-3">
      <h1 className="text-xl font-semibold">Conversation not found</h1>
      <p className="text-sm text-zinc-500">It may have been deleted.</p>
      <Link href="/chat" className="text-blue-600 underline">
        Back to chats
      </Link>
    </div>
  );
}
