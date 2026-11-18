import type { ErrorCode, Plan, ServerFrame, Usage } from "./chat-protocol";

export type MessageStatus = "sending" | "streaming" | "complete" | "stopped" | "error";
export type ChatMessage = {
  key: string; // stable React key: the client id for our own messages, "a<id>" for assistant messages
  id?: number;
  role: "user" | "assistant";
  content: string;
  status: MessageStatus;
};
export type ConnectionStatus = "connecting" | "open" | "closed";

export type ChatState = {
  connection: ConnectionStatus;
  conversationId: string | null;
  messages: ChatMessage[];
  plan: Plan | null;
  usage: Usage | null;
  busy: boolean; // an answer is being generated
  limitReached: boolean;
  error: { code: ErrorCode; message: string } | null;
};

export type ChatAction =
  | { type: "frame"; frame: ServerFrame }
  | { type: "connection"; status: ConnectionStatus }
  | { type: "local.send"; clientId: string; content: string }
  | { type: "local.error"; code: ErrorCode; message: string; clientId?: string }
  | { type: "local.load"; conversationId: string | null; messages: ChatMessage[] }
  | { type: "local.clear_error" };

export const initialChatState: ChatState = {
  connection: "connecting", conversationId: null, messages: [], plan: null, usage: null,
  busy: false, limitReached: false, error: null,
};

const mapMessage = (messages: ChatMessage[], match: (m: ChatMessage) => boolean,
                    change: (m: ChatMessage) => ChatMessage) => messages.map((m) => (match(m) ? change(m) : m));

export function chatReducer(state: ChatState, action: ChatAction): ChatState {
  switch (action.type) {
    case "local.send":
      return { ...state, busy: true, error: null,
        messages: [...state.messages, { key: action.clientId, role: "user", content: action.content, status: "sending" }] };

    case "local.error":
      return failSend(state, action.code, action.message, action.clientId);

    case "local.load":
      return { ...state, conversationId: action.conversationId, messages: action.messages, busy: false, error: null };

    case "local.clear_error":
      return { ...state, error: null };

    case "connection": {
      if (action.status !== "closed") return { ...state, connection: action.status };
      // The server saves a partial answer when the socket drops, so show it as stopped instead of spinning forever.
      return { ...state, connection: "closed", busy: false,
        messages: mapMessage(state.messages, (m) => m.status === "streaming" || m.status === "sending",
          (m) => ({ ...m, status: m.status === "sending" ? "error" : "stopped" })) };
    }

    case "frame":
      return applyFrame(state, action.frame);
  }
}

function failSend(state: ChatState, code: ErrorCode, message: string, clientId?: string): ChatState {
  // A refused message was never accepted: take it off the screen so the user can edit and resend it.
  const messages = clientId
    ? state.messages.filter((m) => !(m.key === clientId && m.status === "sending"))
    : state.messages;
  return { ...state, messages, busy: false, error: { code, message },
           limitReached: state.limitReached || code === "limit_reached" };
}

function applyFrame(state: ChatState, f: ServerFrame): ChatState {
  switch (f.type) {
    case "ready":
      return { ...state, plan: f.plan, usage: f.usage, limitReached: f.usage.used >= f.usage.limit };

    case "chat.started":
      return { ...state, conversationId: f.conversation_id, busy: true,
        messages: [
          ...mapMessage(state.messages, (m) => m.key === f.client_id,
            (m) => ({ ...m, id: f.user_message_id, status: "complete" })),
          { key: `a${f.assistant_message_id}`, id: f.assistant_message_id, role: "assistant", content: "", status: "streaming" },
        ] };

    case "chat.delta":
      return { ...state, messages: mapMessage(state.messages,
        (m) => m.role === "assistant" && m.id === f.assistant_message_id,
        (m) => ({ ...m, content: m.content + f.text })) };

    case "chat.done": {
      const limit = state.usage?.limit ?? 0;
      return { ...state, busy: false,
        usage: state.usage ? { ...state.usage, used: limit - f.remaining } : state.usage,
        limitReached: f.remaining <= 0 && limit > 0,
        messages: mapMessage(state.messages, (m) => m.id === f.assistant_message_id && m.role === "assistant",
          (m) => ({ ...m, status: f.status })) };
    }

    case "chat.error": {
      const next = failSend(state, f.code, f.message, f.client_id);
      if (f.assistant_message_id === undefined) return next;
      return { ...next, messages: mapMessage(next.messages,
        (m) => m.role === "assistant" && m.id === f.assistant_message_id, (m) => ({ ...m, status: "error" })) };
    }

    case "plan.updated":
      return { ...state, plan: f.plan, limitReached: false,
        usage: state.usage ? { ...state.usage, limit: f.plan.daily_message_limit } : state.usage };

    case "pong":
      return state;
  }
}
