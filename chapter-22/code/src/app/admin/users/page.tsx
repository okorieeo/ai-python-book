"use client";

import { Suspense } from "react";

import { RequirePermission } from "@/components/RoleGate";
import { UsersTable } from "@/components/UsersTable";

export default function UsersPage() {
  return (
    <RequirePermission permission="view_users">
      <h1 className="mb-4 text-2xl font-semibold">Users</h1>
      <Suspense>
        <UsersTable />
      </Suspense>
    </RequirePermission>
  );
}
