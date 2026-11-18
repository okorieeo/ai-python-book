// The WebSocket contract between Django (chat/consumers.py) and every client. One file, used by web and mobile.

export type Plan = { code: string; name: string; daily_message_limit: number };
export type Usage = { used: number; limit: number };

export type ErrorCode =
  | "invalid_message" | "too_long" | "limit_reached" | "not_found" | "busy" | "provider_error" | "offline";

export type ServerFrame =
  | { type: "ready"; plan: Plan; usage: Usage }
  | { type: "chat.started"; client_id: string; conversation_id: string; title: string;
      user_message_id: number; assistant_message_id: number }
  | { type: "chat.delta"; assistant_message_id: number; text: string }
  | { type: "chat.done"; assistant_message_id: number; status: "complete" | "stopped";
      usage: { input_tokens: number; output_tokens: number }; remaining: number }
  | { type: "chat.error"; code: ErrorCode; message: string; client_id?: string; assistant_message_id?: number }
  | { type: "plan.updated"; plan: Plan }
  | { type: "pong" };

export type ClientFrame =
  | { type: "chat.send"; conversation_id: string | null; content: string; client_id: string }
  | { type: "chat.stop" }
  | { type: "ping" };

export const CLOSE_UNAUTHORIZED = 4401;
