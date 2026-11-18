"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

export function NewChatButton() {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();
  const [failed, setFailed] = useState(false);

  async function createConversation() {
    setFailed(false);
    try {
      const response = await fetch("/api/conversations", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const conversation = (await response.json()) as { id: string };
      startTransition(() => {
        router.push(`/chat/${conversation.id}`);
        router.refresh(); // ask the server for a fresh sidebar
      });
    } catch {
      setFailed(true);
    }
  }

  return (
    <div>
      <button
        onClick={createConversation}
        disabled={isPending}
        className="w-full rounded-lg bg-blue-600 px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
      >
        {isPending ? "Opening…" : "New chat"}
      </button>
      {failed && (
        <p role="alert" className="mt-1 text-xs text-red-600">
          Could not create a conversation.
        </p>
      )}
    </div>
  );
}
