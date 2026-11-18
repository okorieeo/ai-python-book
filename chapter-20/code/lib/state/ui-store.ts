"use client";

import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";
import { clearDraft, setDraft, type Drafts } from "./drafts";

type UiState = {
  sidebarOpen: boolean;
  drafts: Drafts;
  toggleSidebar: () => void;
  setSidebarOpen: (open: boolean) => void;
  saveDraft: (conversationId: string, text: string) => void;
  discardDraft: (conversationId: string) => void;
};

/** Client-only UI state. Server data (conversations, user) lives in TanStack Query, NOT here. Never store tokens or secrets. */
export const useUiStore = create<UiState>()(
  persist(
    (set) => ({
      sidebarOpen: true,
      drafts: {},
      toggleSidebar: () => set((state) => ({ sidebarOpen: !state.sidebarOpen })),
      setSidebarOpen: (open) => set({ sidebarOpen: open }),
      saveDraft: (conversationId, text) => set((state) => ({ drafts: setDraft(state.drafts, conversationId, text, Date.now()) })),
      discardDraft: (conversationId) => set((state) => ({ drafts: clearDraft(state.drafts, conversationId) })),
    }),
    {
      name: "ai-chat-ui",
      version: 1,
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({ sidebarOpen: state.sidebarOpen, drafts: state.drafts }),   // functions are never persisted
      skipHydration: true,                                                                   // we rehydrate in an effect: no SSR mismatch
    },
  ),
);

/** Call on logout so the next person on a shared computer does not see your unsent drafts. */
export function resetUiStore() {
  useUiStore.setState({ drafts: {}, sidebarOpen: true });
  useUiStore.persist.clearStorage();
}
