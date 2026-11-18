import type { ApiClient } from "./client";
import type { Conversation, Page, User, WsTicket } from "./types";

/** Every backend call the UI makes, typed in one place. Components never write URLs. */
export function createEndpoints(api: ApiClient) {
  return {
    me: (signal?: AbortSignal) => api.get<User>("/me", { signal }),
    listConversations: (params: { limit?: number; cursor?: string | null } = {}, signal?: AbortSignal) =>
      api.get<Page<Conversation>>("/conversations", { query: { limit: params.limit, cursor: params.cursor }, signal }),
    getConversation: (id: string, signal?: AbortSignal) => api.get<Conversation>(`/conversations/${encodeURIComponent(id)}`, { signal }),
    createConversation: (title: string, idempotencyKey: string) =>
      api.post<Conversation>("/conversations", { title }, { idempotencyKey }),
    wsTicket: () => api.post<WsTicket>("/ws-ticket"),
    register: (values: { name: string; email: string; password: string }) => api.post<{ detail: string }>("/auth/register", values),
  };
}
