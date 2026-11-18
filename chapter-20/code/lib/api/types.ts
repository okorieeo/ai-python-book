/** Domain types matching openapi.yaml (Chapter 8). In a real project, generate these with openapi-typescript. */
export type User = { id: string; email: string; name: string };

export type Conversation = { id: string; title: string; created_at: string };

export type Page<T> = { results: T[]; next: string | null };

export type WsTicket = { ticket: string; expires_in: number };
