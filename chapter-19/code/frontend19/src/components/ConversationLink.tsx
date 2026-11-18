"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

export function ConversationLink({ id, title }: { id: string; title: string }) {
  const pathname = usePathname();
  const href = `/chat/${id}`;
  const active = pathname === href;
  return (
    <Link
      href={href}
      aria-current={active ? "page" : undefined}
      className={cn(
        "block truncate rounded-md px-3 py-2 text-sm",
        "focus-visible:ring-ring focus-visible:ring-2 focus-visible:outline-none",
        active ? "bg-accent font-medium" : "hover:bg-muted",
      )}
    >
      {title}
    </Link>
  );
}
