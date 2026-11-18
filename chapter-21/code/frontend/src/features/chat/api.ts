// The ONLY file in this chapter that knows how Chapter 20's API client works.
// If your client has different names, change the imports and these few functions.
import { ApiError, apiFetch } from "@/lib/api/client";
import { FatalSocketError } from "@/lib/realtime/socket";
import type { ChatMessage } from "./chat-state";
import type { ConversationSummary } from "./conversations-cache";

interface ApiMessage {
  id: string;
  client_id?: string | null; // the id the browser chose when it sent the message
  role: "user" | "assistant";
  content: string;
  created_at: string;
}

export function toChatMessage(m: ApiMessage): ChatMessage {
  return {
    id: m.id,
    clientId: m.client_id ?? undefined,
    role: m.role,
    content: m.content,
    createdAt: m.created_at,
    ...(m.role === "user" ? { status: "sent" as const } : {}),
  };
}

export async function fetchMessages(conversationId: string): Promise<ChatMessage[]> {
  const data = await apiFetch<{ results: ApiMessage[] }>(
    `/api/v1/conversations/${conversationId}/messages/`,
  );
  return data.results.map(toChatMessage);
}

/** A short-lived, single-use ticket that lets the browser open the WebSocket. */
export async function fetchWsTicket(): Promise<string> {
  try {
    const data = await apiFetch<{ ticket: string }>("/api/v1/ws-ticket/", { method: "POST" });
    return data.ticket;
  } catch (error) {
    // Signed out: retrying cannot help, so tell the socket to stop trying.
    if (error instanceof ApiError && (error.status === 401 || error.status === 403)) {
      throw new FatalSocketError("Not signed in");
    }
    throw error;
  }
}

export const UPLOAD_URL = `${process.env.NEXT_PUBLIC_API_URL ?? ""}/api/v1/uploads/`;

/** How uploads authenticate. Cookie-based here; return an Authorization header instead if
 *  Chapter 20 keeps the token in memory. */
export async function uploadAuth(): Promise<{
  headers?: Record<string, string>;
  withCredentials?: boolean;
}> {
  return { withCredentials: true };
}

export const renameConversationApi = (id: string, title: string) =>
  apiFetch<ConversationSummary>(`/api/v1/conversations/${id}/`, {
    method: "PATCH",
    body: JSON.stringify({ title }),
  });

export const deleteConversationApi = (id: string) =>
  apiFetch<void>(`/api/v1/conversations/${id}/`, { method: "DELETE" });
