import { Suspense } from "react";
import { NewChatButton } from "@/components/NewChatButton";
import { Sidebar, SidebarSkeleton } from "@/components/Sidebar";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-dvh">
      <aside className="flex w-64 flex-col gap-4 border-r p-3">
        <NewChatButton />
        {/* Data that needs the server is wrapped in Suspense: the page shell
            appears immediately and the list streams in when it is ready. */}
        <Suspense fallback={<SidebarSkeleton />}>
          <Sidebar />
        </Suspense>
      </aside>
      <main className="min-w-0 flex-1">{children}</main>
    </div>
  );
}
