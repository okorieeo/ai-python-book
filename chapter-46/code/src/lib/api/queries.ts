"use client";

import { useQuery } from "@tanstack/react-query";
import { api, unwrap } from "./client";
import type { ChatMessage } from "@/lib/chat/reducer";

export function useConversations() {
  return useQuery({
    queryKey: ["conversations"],
    queryFn: () => unwrap(api.GET("/api/v1/conversations/", { params: { query: {} } })),
  });
}

export function useMessages(conversationId: string) {
  return useQuery({
    queryKey: ["messages", conversationId],
    queryFn: async (): Promise<ChatMessage[]> => {
      const page = await unwrap(
        api.GET("/api/v1/conversations/{public_id}/messages/", {
          params: { path: { public_id: conversationId } },
        }),
      );
      return page.results.map((m) => ({ id: m.public_id, role: m.role, content: m.content }));
    },
  });
}

// Tickets are single-use, so this is a plain function, not a cached query.
export async function fetchSocketUrl(conversationId: string): Promise<string> {
  const { ticket } = await unwrap(api.POST("/api/v1/chat/tickets/"));
  const base = process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000";
  return `${base}/ws/chat/${encodeURIComponent(conversationId)}/?ticket=${encodeURIComponent(ticket)}`;
}
