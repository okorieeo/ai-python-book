"use client";

import Link from "next/link";
import type { ReactNode } from "react";

import { useMe } from "@/hooks/useAdmin";
import { can, homeFor } from "@/lib/permissions";
import type { Permission } from "@/lib/types";

/** Show a piece of UI only to people who hold a permission. Convenience only:
 *  the API refuses the request anyway. */
export function RoleGate({
  permission,
  children,
  fallback = null,
}: {
  permission: Permission;
  children: ReactNode;
  fallback?: ReactNode;
}) {
  const { data: me } = useMe();
  return <>{can(me, permission) ? children : fallback}</>;
}

/** Guard a whole page. While the role is unknown nothing is rendered, and for
 *  the wrong role the page's children never mount, so they never fetch. */
export function RequirePermission({
  permission,
  children,
}: {
  permission: Permission;
  children: ReactNode;
}) {
  const { data: me, isPending } = useMe();
  if (isPending) return null;
  if (!can(me, permission)) return <NotAllowed home={homeFor(me)} />;
  return <>{children}</>;
}

export function NotAllowed({ home }: { home: string | null }) {
  return (
    <div role="alert" className="mx-auto max-w-md py-24 text-center">
      <h1 className="text-xl font-semibold">
        You do not have access to this page
      </h1>
      <p className="mt-2 text-sm text-gray-500">
        Ask an administrator if you think this is a mistake.
      </p>
      {home && (
        <Link
          href={home}
          className="mt-4 inline-block text-sm text-blue-600 underline"
        >
          Go to a page you can open
        </Link>
      )}
    </div>
  );
}
