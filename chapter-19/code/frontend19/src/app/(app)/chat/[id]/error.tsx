"use client";

import { useEffect } from "react";
import { Button } from "@/components/ui/button";

export default function ConversationError({
  error,
  retry,
}: {
  error: unknown;
  retry: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 p-6 text-center">
      <h1 className="text-xl font-semibold">Something went wrong</h1>
      <Button onClick={() => retry()}>Try again</Button>
    </div>
  );
}
