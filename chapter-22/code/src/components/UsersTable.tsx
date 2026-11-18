"use client";

import { useEffect, useState } from "react";

import { RoleGate } from "@/components/RoleGate";
import { DataTable, type Column } from "@/components/DataTable";
import { Pagination } from "@/components/Pagination";
import { useAdminUsers } from "@/hooks/useAdmin";
import { useUrlParams } from "@/hooks/useUrlParams";
import { apiDownload, type Params } from "@/lib/api";
import { formatDate, formatDateTime, formatNumber } from "@/lib/format";
import type { AdminUser } from "@/lib/types";
import { ui } from "@/lib/ui";

const PAGE_SIZE = 20;

const COLUMNS: Column<AdminUser>[] = [
  {
    key: "username",
    header: "User",
    sortKey: "username",
    render: (u) => (
      <>
        <div className="font-medium">{u.username}</div>
        <div className="text-xs text-gray-500">{u.email}</div>
      </>
    ),
  },
  {
    key: "role",
    header: "Role",
    render: (u) => <Badge tone="blue">{u.role}</Badge>,
  },
  {
    key: "active",
    header: "Status",
    render: (u) =>
      u.is_active ? (
        <Badge tone="green">Active</Badge>
      ) : (
        <Badge tone="gray">Inactive</Badge>
      ),
  },
  {
    key: "chats",
    header: "Chats",
    sortKey: "conversation_count",
    align: "right",
    render: (u) => formatNumber(u.conversation_count),
  },
  {
    key: "tokens",
    header: "Tokens (30 days)",
    sortKey: "tokens_30d",
    align: "right",
    render: (u) => formatNumber(u.tokens_30d),
  },
  {
    key: "joined",
    header: "Joined",
    sortKey: "date_joined",
    render: (u) => formatDate(u.date_joined),
  },
  {
    key: "last",
    header: "Last login",
    sortKey: "last_login",
    render: (u) => formatDateTime(u.last_login),
  },
];

function Badge({
  tone,
  children,
}: {
  tone: "blue" | "green" | "gray";
  children: string;
}) {
  const tones = {
    blue: "bg-blue-50 text-blue-700 dark:bg-blue-950 dark:text-blue-300",
    green: "bg-green-50 text-green-700 dark:bg-green-950 dark:text-green-300",
    gray: "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-300",
  };
  return (
    <span
      className={`rounded-full px-2 py-0.5 text-xs font-medium ${tones[tone]}`}
    >
      {children}
    </span>
  );
}

export function UsersTable() {
  const url = useUrlParams();
  const page = Math.max(Number(url.get("page", "1")) || 1, 1);
  const ordering = url.get("ordering", "-date_joined");
  const role = url.get("role");
  const active = url.get("active");

  // Typing is local and instant; the URL (and the request) follow 300 ms later.
  const [text, setText] = useState(url.get("q"));
  const { get, set } = url;
  useEffect(() => {
    const id = setTimeout(() => {
      if (text !== get("q")) set({ q: text });
    }, 300);
    return () => clearTimeout(id);
  }, [text, get, set]);

  const filters: Params = {
    search: url.get("q"),
    role,
    is_active: active,
    ordering,
  };
  const query = useAdminUsers({ ...filters, page, page_size: PAGE_SIZE });
  const [exporting, setExporting] = useState(false);

  async function exportCsv() {
    setExporting(true);
    try {
      await apiDownload("/admin/users/export", filters, "users.csv");
    } finally {
      setExporting(false);
    }
  }

  const field = ui.field;
  return (
    <section>
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <label className="text-sm">
          <span className="sr-only">Search users</span>
          <input
            type="search"
            placeholder="Search name or email"
            value={text}
            onChange={(e) => setText(e.target.value)}
            className={`${field} w-64`}
          />
        </label>
        <label className="text-sm">
          <span className="mr-2 text-gray-500">Role</span>
          <select
            value={role}
            onChange={(e) => set({ role: e.target.value })}
            className={field}
          >
            <option value="">All</option>
            <option value="member">Member</option>
            <option value="support">Support</option>
            <option value="admin">Admin</option>
          </select>
        </label>
        <label className="text-sm">
          <span className="mr-2 text-gray-500">Status</span>
          <select
            value={active}
            onChange={(e) => set({ active: e.target.value })}
            className={field}
          >
            <option value="">All</option>
            <option value="true">Active</option>
            <option value="false">Inactive</option>
          </select>
        </label>
        <RoleGate permission="export_users">
          <button
            onClick={exportCsv}
            disabled={exporting}
            className={`${ui.primary} ml-auto`}
          >
            {exporting ? "Preparing…" : "Export CSV"}
          </button>
        </RoleGate>
      </div>

      {query.isError ? (
        <div
          role="alert"
          className="rounded-xl border border-red-200 p-6 text-sm"
        >
          We could not load the users.{" "}
          <button className="underline" onClick={() => query.refetch()}>
            Try again
          </button>
        </div>
      ) : query.isPending ? (
        <div
          role="status"
          aria-label="Loading users"
          className="h-64 animate-pulse rounded-xl bg-gray-100 dark:bg-gray-800"
        />
      ) : (
        <>
          <DataTable
            caption="Users"
            columns={COLUMNS}
            rows={query.data.results}
            rowKey={(u) => u.id}
            ordering={ordering}
            onOrderingChange={(next) => set({ ordering: next })}
            dimmed={query.isPlaceholderData}
            empty="No users match these filters."
          />
          <Pagination
            page={page}
            pageSize={PAGE_SIZE}
            count={query.data.count}
            onPage={(p) => set({ page: String(p) })}
          />
        </>
      )}
    </section>
  );
}
