import type { Metadata } from "next";

export const metadata: Metadata = { title: "Chat" };

export default function ChatIndexPage() {
  return (
    <div className="flex h-full items-center justify-center text-zinc-500">
      Choose a conversation, or start a new one.
    </div>
  );
}
