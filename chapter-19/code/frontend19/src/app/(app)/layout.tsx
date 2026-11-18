import { Suspense } from "react";
import { MobileNav } from "@/components/MobileNav";
import { NewChatButton } from "@/components/NewChatButton";
import { Sidebar, SidebarSkeleton } from "@/components/Sidebar";
import { ThemeToggle } from "@/components/ThemeToggle";

function Conversations() {
  return (
    <>
      <NewChatButton />
      <Suspense fallback={<SidebarSkeleton />}>
        <Sidebar />
      </Suspense>
    </>
  );
}

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-dvh flex-col md:flex-row">
      {/* Phones: a top bar with a menu button. */}
      <header className="flex items-center justify-between border-b px-2 py-1 md:hidden">
        <MobileNav>
          <Conversations />
        </MobileNav>
        <span className="font-semibold">Chat App</span>
        <ThemeToggle />
      </header>

      {/* Tablets and larger: a permanent sidebar. */}
      <aside className="hidden w-64 shrink-0 flex-col gap-4 border-r p-3 md:flex">
        <Conversations />
        <div className="mt-auto">
          <ThemeToggle />
        </div>
      </aside>

      <main id="main" className="min-h-0 min-w-0 flex-1">
        {children}
      </main>
    </div>
  );
}
