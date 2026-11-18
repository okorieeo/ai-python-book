import type { ServerEvent } from "@/lib/realtime/protocol";

export type FinishReason = "stop" | "length" | "stopped" | "error" | "interrupted";
export type SendStatus = "sending" | "sent" | "failed";

export interface ChatMessage {
  id: string; // while a user message is "sending" this is the client id; later the server id
  clientId?: string; // our own id for the message, kept so retries and history can be matched
  role: "user" | "assistant";
  content: string;
  createdAt: string;
  status?: SendStatus; // user messages
  streaming?: boolean; // assistant messages
  finishReason?: FinishReason;
  error?: string;
  attachmentIds?: string[];
  sentAt?: number; // ms timestamp, used for the "no acknowledgement" timeout
}

/** What we know locally that the server has not confirmed in the message history yet. */
export interface LiveConversation {
  messages: ChatMessage[];
  generatingId: string | null; // the assistant message being streamed right now
  awaitingReply: boolean; // a user message was sent and no assistant reply has started
  error: { code: string; message: string; retryAfter?: number } | null;
}

export type ChatState = Record<string, LiveConversation>;

export type ChatAction =
  | {
      type: "local/send"; conversationId: string; clientId: string;
      content: string; now: number; attachmentIds?: string[];
    }
  | { type: "local/resend"; conversationId: string; clientId: string; now: number }
  | { type: "local/fail"; conversationId: string; clientId: string; reason: string }
  | { type: "local/dismiss_error"; conversationId: string }
  | { type: "connection/lost" }
  | { type: "prune"; conversationId: string; confirmedIds: string[] }
  | { type: "server"; event: ServerEvent };

export const initialChatState: ChatState = {};

const emptyConversation = (): LiveConversation => ({
  messages: [],
  generatingId: null,
  awaitingReply: false,
  error: null,
});

const matches = (m: ChatMessage, clientId: string) =>
  m.id === clientId || m.clientId === clientId;
const isSending = (m: ChatMessage, clientId: string) =>
  matches(m, clientId) && m.status === "sending";
const DROPPED = "The connection dropped before this was sent.";

function update(
  state: ChatState,
  conversationId: string,
  change: (conv: LiveConversation) => LiveConversation,
): ChatState {
  const current = state[conversationId] ?? emptyConversation();
  const next = change(current);
  if (next === current && state[conversationId]) return state;
  return { ...state, [conversationId]: next };
}

function mapMessage(
  conv: LiveConversation,
  test: (m: ChatMessage) => boolean,
  change: (m: ChatMessage) => ChatMessage,
): LiveConversation {
  if (!conv.messages.some(test)) return conv;
  return { ...conv, messages: conv.messages.map((m) => (test(m) ? change(m) : m)) };
}

function findConversationByClientId(state: ChatState, clientId: string): string | null {
  for (const [id, conv] of Object.entries(state)) {
    if (conv.messages.some((m) => matches(m, clientId))) return id;
  }
  return null;
}

function findConversationOf(state: ChatState, messageId: string): string | null {
  for (const [id, conv] of Object.entries(state)) {
    if (conv.messages.some((m) => m.id === messageId)) return id;
  }
  return null;
}

export function chatReducer(state: ChatState, action: ChatAction): ChatState {
  switch (action.type) {
    case "local/send":
      return update(state, action.conversationId, (conv) => ({
        ...conv,
        messages: [
          ...conv.messages,
          {
            id: action.clientId,
            clientId: action.clientId,
            role: "user",
            content: action.content,
            createdAt: new Date(action.now).toISOString(),
            status: "sending",
            sentAt: action.now,
            attachmentIds: action.attachmentIds,
          },
        ],
        awaitingReply: true,
        error: null,
      }));

    case "local/resend":
      return update(state, action.conversationId, (conv) => ({
        ...mapMessage(conv, (m) => matches(m, action.clientId), (m) => ({
          ...m, status: "sending", error: undefined, sentAt: action.now,
        })),
        awaitingReply: true,
        error: null,
      }));

    case "local/fail":
      return update(state, action.conversationId, (conv) => ({
        ...mapMessage(conv, (m) => isSending(m, action.clientId), (m) => ({
          ...m, status: "failed", error: action.reason,
        })),
        awaitingReply: false,
      }));

    case "local/dismiss_error":
      return update(state, action.conversationId, (conv) =>
        conv.error ? { ...conv, error: null } : conv,
      );

    case "connection/lost": {
      let next = state;
      for (const [id, conv] of Object.entries(state)) {
        const dirty = conv.generatingId !== null || conv.awaitingReply ||
          conv.messages.some((m) => m.status === "sending");
        if (!dirty) continue;
        next = {
          ...next,
          [id]: {
            ...conv,
            generatingId: null,
            awaitingReply: false,
            messages: conv.messages.map((m) =>
              m.streaming
                ? { ...m, streaming: false, finishReason: "interrupted" as const }
                : m.status === "sending"
                  ? { ...m, status: "failed" as const, error: DROPPED }
                  : m),
          },
        };
      }
      return next;
    }

    case "prune": {
      const confirmed = new Set(action.confirmedIds);
      return update(state, action.conversationId, (conv) => {
        const settled = (m: ChatMessage) =>
          !m.streaming && m.status !== "sending" && m.status !== "failed";
        const keep = conv.messages.filter((m) => !(confirmed.has(m.id) && settled(m)));
        return keep.length === conv.messages.length ? conv : { ...conv, messages: keep };
      });
    }

    case "server":
      return applyServerEvent(state, action.event);
  }
}

function applyServerEvent(state: ChatState, event: ServerEvent): ChatState {
  switch (event.type) {
    case "message.accepted": {
      const { client_id: clientId, message } = event;
      return update(state, event.conversation_id, (conv) => {
        if (conv.messages.some((m) => m.id === message.id)) return conv; // duplicate ack
        const known = conv.messages.some((m) => matches(m, clientId));
        const confirmed: ChatMessage = {
          id: message.id, clientId, role: "user", content: message.content,
          createdAt: message.created_at, status: "sent",
        };
        return known
          ? mapMessage(conv, (m) => matches(m, clientId), (m) => ({
              ...m, ...confirmed, attachmentIds: m.attachmentIds, error: undefined,
            }))
          : { ...conv, messages: [...conv.messages, confirmed] };
      });
    }

    case "assistant.start":
      return update(state, event.conversation_id, (conv) => {
        if (conv.messages.some((m) => m.id === event.message_id)) return conv;
        return {
          ...conv,
          messages: [...conv.messages, {
            id: event.message_id, role: "assistant", content: "",
            createdAt: event.created_at ?? "", streaming: true,
          }],
          generatingId: event.message_id,
          awaitingReply: false,
          error: null,
        };
      });

    case "assistant.delta": {
      const conversationId = findConversationOf(state, event.message_id);
      if (!conversationId || event.delta === "") return state;
      return update(state, conversationId, (conv) =>
        mapMessage(conv, (m) => m.id === event.message_id && m.streaming === true, (m) => ({
          ...m, content: m.content + event.delta,
        })),
      );
    }

    case "assistant.end": {
      const conversationId = findConversationOf(state, event.message_id);
      if (!conversationId) return state;
      return update(state, conversationId, (conv) => ({
        ...mapMessage(conv, (m) => m.id === event.message_id, (m) => ({
          ...m, streaming: false, finishReason: event.finish_reason,
        })),
        generatingId: conv.generatingId === event.message_id ? null : conv.generatingId,
      }));
    }

    case "error": {
      const { client_id: clientId } = event;
      const conversationId =
        event.conversation_id ??
        (clientId ? findConversationByClientId(state, clientId) : null);
      if (!conversationId) return state;
      const error = {
        code: event.code, message: event.message, retryAfter: event.retry_after,
      };
      return update(state, conversationId, (conv) =>
        clientId
          ? {
              // a send was rejected (for example rate limited): fail just that message
              ...mapMessage(conv, (m) => isSending(m, clientId), (m) => ({
                ...m, status: "failed", error: event.message,
              })),
              awaitingReply: false,
              error,
            }
          : {
              // the generation itself failed: stop the stream where it is
              ...mapMessage(conv, (m) => m.streaming === true, (m) => ({
                ...m, streaming: false, finishReason: "error",
              })),
              generatingId: null,
              awaitingReply: false,
              error,
            },
      );
    }

    case "pong":
      return state;
  }
}

/** History from the server first, then local messages the server has not confirmed yet. */
export function mergeForDisplay(history: ChatMessage[], live: ChatMessage[]): ChatMessage[] {
  const ids = new Set(history.map((m) => m.id));
  const clientIds = new Set(history.map((m) => m.clientId).filter((x): x is string => !!x));
  const seen = (m: ChatMessage) =>
    ids.has(m.id) || (m.clientId !== undefined && clientIds.has(m.clientId));
  const extra = live.filter((m) => !seen(m));
  return extra.length === 0 ? history : [...history, ...extra];
}

/** User messages that were sent but never acknowledged within `ttlMs`. */
export function findStaleSending(state: ChatState, now: number, ttlMs: number) {
  const stale: { conversationId: string; clientId: string }[] = [];
  for (const [conversationId, conv] of Object.entries(state)) {
    for (const m of conv.messages) {
      if (m.status === "sending" && m.sentAt !== undefined && now - m.sentAt >= ttlMs) {
        stale.push({ conversationId, clientId: m.clientId ?? m.id });
      }
    }
  }
  return stale;
}
