import { useCallback, useEffect, useReducer, useRef } from "react";

import { ChatClient, UnauthorizedError } from "./chat-client";
import type { ErrorCode } from "./chat-protocol";
import { chatReducer, initialChatState, type ChatMessage } from "./chat-state";

export type UseChatOptions = {
  apiBase: string; // e.g. https://api.example.com/api/v1
  wsUrl: string; // e.g. wss://api.example.com/ws/chat/
  getAccessToken: () => Promise<string | null>;
  onUnauthorized: () => void; // send the user to the login screen
};

const makeId = () => `c${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`; // works in React Native too

export function useChat(options: UseChatOptions) {
  const [state, dispatch] = useReducer(chatReducer, initialChatState);
  const client = useRef<ChatClient | null>(null);
  const conversationId = useRef<string | null>(null);
  conversationId.current = state.conversationId;
  const opts = useRef(options);
  opts.current = options;

  useEffect(() => {
    const c = new ChatClient({
      wsUrl: options.wsUrl,
      onFrame: (frame) => dispatch({ type: "frame", frame }),
      onStatus: (status) => dispatch({ type: "connection", status }),
      onUnauthorized: () => opts.current.onUnauthorized(),
      getTicket: async () => {
        const token = await opts.current.getAccessToken();
        if (!token) throw new UnauthorizedError();
        const res = await fetch(`${opts.current.apiBase}/auth/ws-ticket/`, {
          method: "POST", headers: { Authorization: `Bearer ${token}` } });
        if (res.status === 401) throw new UnauthorizedError();
        if (!res.ok) throw new Error(`ticket request failed (${res.status})`);
        return (await res.json()).ticket as string;
      },
    });
    client.current = c;
    c.connect();
    return () => { c.close(); client.current = null; };
  }, [options.wsUrl]);

  const send = useCallback((content: string) => {
    const text = content.trim();
    if (!text) return false;
    const clientId = makeId();
    const sent = client.current?.send({ type: "chat.send", conversation_id: conversationId.current, content: text, client_id: clientId });
    if (!sent) {
      dispatch({ type: "local.error", code: "offline", message: "You are offline. Reconnecting…" });
      return false;
    }
    dispatch({ type: "local.send", clientId: clientId, content: text });
    return true;
  }, []);

  const stop = useCallback(() => { client.current?.send({ type: "chat.stop" }); }, []);

  const openConversation = useCallback(async (id: string | null) => {
    if (id === null) return dispatch({ type: "local.load", conversationId: null, messages: [] });
    const token = await opts.current.getAccessToken();
    const res = await fetch(`${opts.current.apiBase}/conversations/${id}/messages/`, {
      headers: { Authorization: `Bearer ${token}` } });
    if (res.status === 401) return opts.current.onUnauthorized();
    if (!res.ok) return dispatch({ type: "local.error", code: "not_found" as ErrorCode, message: "Could not load that conversation." });
    const rows = (await res.json()) as { id: number; role: "user" | "assistant"; content: string; status: string }[];
    const messages: ChatMessage[] = rows.map((r) => ({
      key: `m${r.id}`, id: r.id, role: r.role, content: r.content,
      status: r.status === "stopped" ? "stopped" : r.status === "error" ? "error" : "complete" }));
    dispatch({ type: "local.load", conversationId: id, messages });
  }, []);

  return { state, send, stop, openConversation, clearError: () => dispatch({ type: "local.clear_error" }) };
}
