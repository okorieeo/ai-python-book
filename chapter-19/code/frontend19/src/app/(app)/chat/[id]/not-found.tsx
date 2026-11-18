import Link from "next/link";
import { Button } from "@/components/ui/button";

export default function ConversationNotFound() {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 p-6 text-center">
      <h1 className="text-xl font-semibold">Conversation not found</h1>
      <p className="text-muted-foreground text-sm">It may have been deleted.</p>
      <Button asChild>
        <Link href="/chat">Back to chats</Link>
      </Button>
    </div>
  );
}
