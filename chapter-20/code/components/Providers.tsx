"use client";

import { QueryCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useEffect, useState, type ReactNode } from "react";
import { ApiError } from "@/lib/api/errors";
import { retryDelay, shouldRetry } from "@/lib/query/retry";
import { useUiStore } from "@/lib/state/ui-store";

export function Providers({ children }: { children: ReactNode }) {
  // Create the client once per browser tab (useState keeps it across re-renders)
  const [queryClient] = useState(() => {
    const client: QueryClient = new QueryClient({
      queryCache: new QueryCache({
        onError: (error) => {
          // One place handles "your session is over" for EVERY query in the app
          if (error instanceof ApiError && error.code === "session_expired") {
            client.clear();
            window.location.assign("/login");
          }
        },
      }),
      defaultOptions: {
        queries: { staleTime: 30_000, retry: shouldRetry, retryDelay, refetchOnWindowFocus: true },
        mutations: { retry: false },          // never retry a write automatically; use an idempotency key and let the user retry
      },
    });
    return client;
  });

  // The UI store is persisted in localStorage, so it can only be restored in the browser, after the first render
  useEffect(() => {
    void useUiStore.persist.rehydrate();
  }, []);

  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}
