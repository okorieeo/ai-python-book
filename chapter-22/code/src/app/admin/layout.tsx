"use client";

import { useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { Sidebar } from "@/components/Sidebar";
import { useMe } from "@/hooks/useAdmin";
import { ApiError } from "@/lib/api";

export default function AdminLayout({ children }: { children: ReactNode }) {
  const router = useRouter();
  const { data: me, error, isPending } = useMe();

  useEffect(() => {
    if (error instanceof ApiError && error.status === 401)
      router.replace("/login");
  }, [error, router]);

  if (isPending) {
    return (
      <div
        role="status"
        aria-label="Loading"
        className="m-8 h-8 w-40 animate-pulse rounded bg-gray-200"
      />
    );
  }
  if (!me) return null; // not signed in: the effect above is redirecting

  return (
    <div className="flex min-h-screen">
      <Sidebar me={me} />
      <main className="flex-1 p-6">{children}</main>
    </div>
  );
}
