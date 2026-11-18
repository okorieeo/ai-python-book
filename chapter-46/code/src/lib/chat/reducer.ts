import type { ServerEvent } from "./protocol";

export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  pending?: boolean; // true while tokens are still arriving
};

export type ChatState = {
  messages: ChatMessage[];
  status: "idle" | "streaming" | "error";
  error: { code: string; message: string } | null;
};

export type ChatAction =
  | { type: "history_loaded"; messages: ChatMessage[] }
  | { type: "user_sent"; id: string; content: string }
  | { type: "server_event"; event: ServerEvent }
  | { type: "connection_lost" };

export const initialChatState: ChatState = { messages: [], status: "idle", error: null };

function lastIsPendingAssistant(messages: ChatMessage[]): boolean {
  const last = messages.at(-1);
  return last?.role === "assistant" && last.pending === true;
}

// A pure function: the same state and action always give the same result,
// so every streaming edge case can be tested without a socket or a browser.
export function chatReducer(state: ChatState, action: ChatAction): ChatState {
  switch (action.type) {
    case "history_loaded":
      return { ...initialChatState, messages: action.messages };

    case "user_sent":
      return {
        messages: [
          ...state.messages,
          { id: action.id, role: "user", content: action.content },
          { id: `${action.id}-reply`, role: "assistant", content: "", pending: true },
        ],
        status: "streaming",
        error: null,
      };

    case "server_event": {
      const { event } = action;
      if (event.type === "token") {
        if (!lastIsPendingAssistant(state.messages)) return state; // a stray frame after done/error
        const messages = state.messages.slice(0, -1);
        const last = state.messages.at(-1)!;
        return { ...state, messages: [...messages, { ...last, content: last.content + event.delta }] };
      }
      if (event.type === "done") {
        if (!lastIsPendingAssistant(state.messages)) return state;
        const last = state.messages.at(-1)!;
        return {
          ...state,
          status: "idle",
          messages: [...state.messages.slice(0, -1), { ...last, id: event.message_id, pending: false }],
        };
      }
      // error: keep whatever text arrived, mark it finished, and surface the error
      const messages = lastIsPendingAssistant(state.messages)
        ? [...state.messages.slice(0, -1), { ...state.messages.at(-1)!, pending: false }]
        : state.messages;
      return { messages, status: "error", error: { code: event.code, message: event.message } };
    }

    case "connection_lost": {
      if (state.status !== "streaming") return state;
      const messages = lastIsPendingAssistant(state.messages)
        ? [...state.messages.slice(0, -1), { ...state.messages.at(-1)!, pending: false }]
        : state.messages;
      return {
        messages,
        status: "error",
        error: { code: "connection_lost", message: "The connection dropped before the reply finished." },
      };
    }
  }
}
