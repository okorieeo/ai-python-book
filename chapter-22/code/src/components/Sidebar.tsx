"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { visibleNav } from "@/lib/permissions";
import type { Me } from "@/lib/types";
import { ui } from "@/lib/ui";

export function Sidebar({ me }: { me: Me }) {
  const pathname = usePathname();
  return (
    <aside className={ui.sidebar}>
      <p className="mb-6 text-lg font-semibold">Admin</p>
      <nav aria-label="Main" className="flex flex-col gap-1">
        {visibleNav(me).map((item) => {
          const current = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              aria-current={current ? "page" : undefined}
              className={`rounded-md px-3 py-2 text-sm ${
                current
                  ? ui.navCurrent
                  : "hover:bg-gray-100 dark:hover:bg-gray-800"
              }`}
            >
              {item.label}
            </Link>
          );
        })}
      </nav>
      <div className="mt-auto text-xs text-gray-500">
        <p className="font-medium text-gray-700 dark:text-gray-300">
          {me.username}
        </p>
        <p>{me.role}</p>
      </div>
    </aside>
  );
}
