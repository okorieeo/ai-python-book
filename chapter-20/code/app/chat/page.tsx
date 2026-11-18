"use client";

import { ConversationList } from "@/components/chat/ConversationList";
import { NewConversationForm } from "@/components/forms/NewConversationForm";
import { LogoutButton } from "@/components/LogoutButton";
import { useMe } from "@/lib/query/hooks";
import { useUiStore } from "@/lib/state/ui-store";

export default function ChatPage() {
  const me = useMe();
  const sidebarOpen = useUiStore((state) => state.sidebarOpen);          // a selector: re-render only when THIS value changes
  const toggleSidebar = useUiStore((state) => state.toggleSidebar);

  return (
    <main>
      <header>
        <h1>Chat</h1>
        <span>{me.data ? `Signed in as ${me.data.email}` : null}</span>
        <button onClick={toggleSidebar} aria-expanded={sidebarOpen}>{sidebarOpen ? "Hide" : "Show"} conversations</button>
        <LogoutButton />
      </header>
      {sidebarOpen ? (
        <aside>
          <NewConversationForm />
          <ConversationList />
        </aside>
      ) : null}
    </main>
  );
}
