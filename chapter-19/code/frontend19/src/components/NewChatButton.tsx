"use client";

import { Plus } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { Button } from "@/components/ui/button";

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
        router.refresh();
      });
    } catch {
      setFailed(true);
    }
  }

  return (
    <div>
      <Button
        onClick={createConversation}
        disabled={isPending}
        className="w-full"
      >
        <Plus aria-hidden="true" />
        {isPending ? "Opening…" : "New chat"}
      </Button>
      {failed && (
        <p role="alert" className="text-destructive mt-1 text-xs">
          Could not create a conversation.
        </p>
      )}
    </div>
  );
}
