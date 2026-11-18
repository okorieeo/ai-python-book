// The contract between the Django WebSocket (assistant/consumers.py) and every client.
// Web and mobile import THIS file, so they cannot drift apart.

export type ClientMessage =
  | { type: "message"; text: string }
  | { type: "decision"; action_id: string; approve: boolean };

export type PendingAction = { action_id: string; tool: string; summary: string };

export type ServerEvent =
  | { type: "assistant.text_delta"; text: string }
  | { type: "assistant.tool_started"; tool: string }
  | { type: "assistant.tool_finished"; tool: string; ok: boolean }
  | { type: "assistant.done"; status: string; text: string; pending: PendingAction[] }
  | { type: "assistant.error"; code: string; message: string };

export type ToolActivity = { tool: string; state: "running" | "done" | "failed" };

export type ChatItem = {
  id: number;
  role: "user" | "assistant";
  text: string;
  streaming: boolean;
  tools: ToolActivity[];
};

export type PendingView = PendingAction & { sending: boolean };

export type ChatState = {
  items: ChatItem[];
  pending: PendingView[];
  busy: boolean;
  error: string | null;
  nextId: number;
};

export type ChatAction =
  | { kind: "user_sent"; text: string }
  | { kind: "decision_sent"; actionId: string }
  | { kind: "server"; event: ServerEvent }
  | { kind: "reset" };

export const initialChatState: ChatState = { items: [], pending: [], busy: false, error: null, nextId: 1 };

const TOOL_LABELS: Record<string, string> = {
  list_tasks: "Checking your tasks",
  list_events: "Checking your calendar",
  find_free_slots: "Looking for free time",
  plan_my_day: "Planning your day",
  create_task: "Adding a task",
  update_task: "Updating a task",
  complete_task: "Completing a task",
  create_event: "Adding an event",
  reschedule_event: "Moving an event",
  delete_task: "Preparing to delete a task",
  delete_event: "Preparing to delete an event",
};

/** A friendly label for the activity chip. Unknown tools get a neutral label, never the raw name. */
export function describeTool(tool: string): string {
  return TOOL_LABELS[tool] ?? "Working";
}

function lastStreaming(state: ChatState): ChatItem | undefined {
  const last = state.items[state.items.length - 1];
  return last && last.role === "assistant" && last.streaming ? last : undefined;
}

/** Update the streaming assistant item, creating it first if this is the start of a reply. */
function withStreamingItem(state: ChatState, change: (item: ChatItem) => ChatItem): ChatState {
  const current = lastStreaming(state);
  if (current) {
    return { ...state, items: state.items.map((i) => (i === current ? change(i) : i)) };
  }
  const fresh: ChatItem = { id: state.nextId, role: "assistant", text: "", streaming: true, tools: [] };
  return { ...state, items: [...state.items, change(fresh)], nextId: state.nextId + 1 };
}

export function chatReducer(state: ChatState, action: ChatAction): ChatState {
  switch (action.kind) {
    case "reset":
      return initialChatState;

    case "user_sent":
      return {
        ...state,
        error: null,
        busy: true,
        items: [...state.items, { id: state.nextId, role: "user", text: action.text, streaming: false, tools: [] }],
        nextId: state.nextId + 1,
      };

    case "decision_sent":
      return {
        ...state,
        busy: true,
        error: null,
        pending: state.pending.map((p) => (p.action_id === action.actionId ? { ...p, sending: true } : p)),
      };

    case "server": {
      const event = action.event;
      switch (event.type) {
        case "assistant.text_delta":
          return withStreamingItem(state, (i) => ({ ...i, text: i.text + event.text }));

        case "assistant.tool_started":
          return withStreamingItem(state, (i) => ({ ...i, tools: [...i.tools, { tool: event.tool, state: "running" }] }));

        case "assistant.tool_finished":
          return withStreamingItem(state, (i) => {
            const index = i.tools.findIndex((t) => t.tool === event.tool && t.state === "running");
            if (index < 0) return i;
            const tools = i.tools.map((t, n) => (n === index ? { ...t, state: event.ok ? ("done" as const) : ("failed" as const) } : t));
            return { ...i, tools };
          });

        case "assistant.done": {
          // The final text is authoritative: it replaces any "let me check..." narration streamed along the way.
          const current = lastStreaming(state);
          const finalText = event.text || current?.text || "";
          let next: ChatState;
          if (current) {
            next = { ...state, items: state.items.map((i) => (i === current ? { ...i, text: finalText, streaming: false } : i)) };
          } else if (finalText) {
            next = {
              ...state,
              items: [...state.items, { id: state.nextId, role: "assistant", text: finalText, streaming: false, tools: [] }],
              nextId: state.nextId + 1,
            };
          } else {
            next = state;
          }
          return { ...next, busy: false, pending: event.pending.map((p) => ({ ...p, sending: false })) };
        }

        case "assistant.error": {
          const current = lastStreaming(state);
          const items = current ? state.items.map((i) => (i === current ? { ...i, streaming: false } : i)) : state.items;
          return { ...state, items, busy: false, error: event.message };
        }
      }
    }
  }
}
