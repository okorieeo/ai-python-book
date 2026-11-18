import type { Metadata } from "next";

export const metadata: Metadata = { title: "Chat" };

export default function ChatIndexPage() {
  return (
    <div className="text-muted-foreground flex h-full items-center justify-center p-6 text-center">
      Choose a conversation, or start a new one.
    </div>
  );
}
