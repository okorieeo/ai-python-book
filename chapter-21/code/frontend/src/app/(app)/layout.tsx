import type { ReactNode } from "react";
import { ChatSocketProvider } from "@/features/chat/chat-socket-provider";

// Mounted in the layout, not in a page: the layout survives navigation between
// conversations, so there is ONE socket per browser tab for the whole signed-in area.
export default function AppLayout({ children }: { children: ReactNode }) {
  return <ChatSocketProvider>{children}</ChatSocketProvider>;
}
