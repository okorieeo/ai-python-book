"use client"; // error boundaries must be Client Components

import { useEffect } from "react";

export default function ConversationError({
  error,
  retry,
}: {
  error: unknown;
  retry: () => void;
}) {
  useEffect(() => {
    console.error(error); // later: send to an error-reporting service
  }, [error]);

  return (
    <div className="flex h-full flex-col items-center justify-center gap-3">
      <h1 className="text-xl font-semibold">Something went wrong</h1>
      <button
        onClick={() => retry()}
        className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white"
      >
        Try again
      </button>
    </div>
  );
}
