"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export function ConversationLink({ id, title }: { id: string; title: string }) {
  const pathname = usePathname();
  const href = `/chat/${id}`;
  const active = pathname === href;
  return (
    <Link
      href={href}
      aria-current={active ? "page" : undefined}
      className={`block truncate rounded-md px-3 py-2 text-sm ${
        active ? "bg-zinc-200 font-medium" : "hover:bg-zinc-100"
      }`}
    >
      {title}
    </Link>
  );
}
