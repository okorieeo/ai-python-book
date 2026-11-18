import { create } from "zustand";
import { chatReducer, initialChatState, type ChatAction, type ChatState } from "./chat-state";

interface ChatStore {
  state: ChatState;
  dispatch: (action: ChatAction) => void;
}

/** Holds the state and runs the pure reducer. All the logic is in chat-state.ts. */
export const useChatStore = create<ChatStore>()((set) => ({
  state: initialChatState,
  dispatch: (action) => set((store) => ({ state: chatReducer(store.state, action) })),
}));
