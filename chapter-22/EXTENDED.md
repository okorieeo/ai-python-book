# Chapter 22 — Dashboards, Admin Panels and Data Visualization: extended material

The printed edition of *Building AI-Powered Apps* keeps each chapter short. This file holds the longer material that was moved here so that nothing is lost: the full hands-on lab, troubleshooting tables, checklists, further exercises, and sections that were condensed for print.


---

# Sections condensed for print


## The Backend for a Dashboard › CSV export

**python  api/v1/admin_views.py (export)**

```python
    @extend_schema(summary="Download the filtered users as CSV",
                   responses={(200, "text/csv"): OpenApiTypes.STR})
    @action(detail=False, url_path="export",
            permission_classes=[IsAuthenticated, has_permission("export_users")])
    def export(self, request):
        columns = ["username", "email", "role", "is_active", "date_joined",
                   "last_login", "conversation_count", "tokens_30d"]
        rows = self.filter_queryset(self.get_queryset())

        def lines():
            buffer = io.StringIO()
            writer = csv.writer(buffer)
            writer.writerow(columns)
            for user in rows.iterator(chunk_size=500):    # never load all rows
                writer.writerow([safe_cell(getattr(user, c)) for c in columns])
                yield buffer.getvalue()
                buffer.seek(0)
                buffer.truncate(0)

        response = StreamingHttpResponse(lines(), content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="users.csv"'
        return response
```

- **It follows the table.**  `self.filter_queryset(self.get_queryset())` applies the same search, filters and ordering, so "Export CSV" downloads what the admin is looking at, not the whole table.
- **It streams.**  `StreamingHttpResponse` and `.iterator(chunk_size=500)` send rows as they are read, so exporting 500,000 users does not build a 100 MB string in memory.
- **It is rate limited** with the `export` throttle scope (5 per minute), set in `get_throttles` the same way as `ai_chat` in Chapter 12. Exports are expensive.
- **Its permission is stricter** than the table’s: `export_users`, which support staff do not have.
- `safe_cell` **defuses CSV injection.** If a user registers with the name `=HYPERLINK("http://evil")`, a spreadsheet opens the file and **runs it as a formula** on the administrator’s computer. Prefixing cells that start with `=`, `+`, `-`, `@`, tab or carriage return with a single quote makes them plain text. A test creates exactly that user and checks the export.
**response**

```
GET /api/v1/admin/users/export?role=support
HTTP/1.1 200 OK
Content-Type: text/csv
Content-Disposition: attachment; filename="users.csv"

username,email,role,is_active,date_joined,last_login,
  conversation_count,tokens_30d
demo_support,demo_support@example.com,support,True,
  2026-11-04 03:44:42+00:00,2026-11-04 03:45:06+00:00,0,0
```

> **A subtle bug we found while writing this chapter**
>
> SimpleJWT does not update `last_login` by default, so a "Last login" column in the admin table would say "Never" for every user forever. The fix is one setting, `"UPDATE_LAST_LOGIN": True` in `SIMPLE_JWT`, and a test that logs in and checks the field. Always check that the data behind a column is actually being written.


## Fetching and Caching Data

Every component in this chapter gets its data the same way: one small fetch wrapper, one hook per endpoint, and TanStack Query in between to cache, deduplicate and retry. The wrapper is the only file that knows the API’s address and error format:

**typescript  src/lib/api.ts**

```typescript
import { getAccessToken } from "./auth";

export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public fields?: Record<string, string[]>,
  ) {
    super(message);
  }
}

export type Params = Record<
  string,
  string | number | boolean | null | undefined
>;

/** ?a=1&b=x, leaving out anything empty so URLs stay clean. */
export function buildQuery(params: Params = {}): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

async function request(path: string, init: RequestInit, params?: Params) {
  const token = getAccessToken();
  const response = await fetch(
    `${API_URL}/api/v1${path}${buildQuery(params)}`,
    {
      ...init,
      headers: {
        Accept: "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...init.headers,
      },
    },
  );
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const error = body?.error;
    throw new ApiError(
      response.status,
      error?.code ?? "error",
      error?.message ?? response.statusText,
      error?.fields,
    );
  }
  return response;
}

export async function apiGet<T>(path: string, params?: Params): Promise<T> {
  return (await request(path, {}, params)).json();
}

export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const response = await request(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return response.json();
}

/** Fetch a file with the auth header, then hand it to the browser. */
export async function apiDownload(
  path: string,
  params: Params,
  filename: string,
) {
  const blob = await (await request(path, {}, params)).blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}
```

- `ApiError` carries the HTTP `status`, the stable `code` and the per-field errors of the error shape from Chapter 8. UI code can write `error.status === 403` instead of parsing text.
- `buildQuery` **leaves out empty values**, so `{ page: 2, search: "", role: null }` becomes `?page=2`. URLs stay short, and caches do not see two different keys for the same request. `URLSearchParams` also encodes `&` and spaces safely.
- `apiDownload` **fetches the file with the auth header** and then hands the blob to the browser. A plain `<a href="/export">` cannot send an `Authorization` header, so a link would get `401`.
- **The token comes from one function,**  `getAccessToken()`. In this chapter it is a development stand-in that keeps the token in memory (shown in Chapter 22); Chapter 20 replaces it with the real flow, and nothing else in the dashboard changes.
The types mirror the API. Chapter 20 generates them from the OpenAPI file; here we write the few we need by hand so you can see the shapes (the full file is in the book’s repository). Then one hook per endpoint:

**typescript  src/hooks/useAdmin.ts**

```typescript
"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { apiGet, type Params } from "@/lib/api";
import type {
  AdminUser,
  Me,
  Overview,
  Page,
  StatusCount,
  TopUser,
  UsageSeries,
} from "@/lib/types";

export const useMe = () =>
  useQuery({
    queryKey: ["me"],
    queryFn: () => apiGet<Me>("/me"),
    staleTime: 60_000,
  });

export const useOverview = () =>
  useQuery({
    queryKey: ["admin", "overview"],
    queryFn: () => apiGet<Overview>("/admin/overview"),
    refetchInterval: 60_000, // numbers on a wall screen stay fresh
  });

export const useUsageSeries = (days: number) =>
  useQuery({
    queryKey: ["admin", "usage", days],
    queryFn: () => apiGet<UsageSeries>("/admin/usage", { days }),
    placeholderData: keepPreviousData, // no flash when the range changes
  });

export const useTopUsers = (days: number) =>
  useQuery({
    queryKey: ["admin", "top-users", days],
    queryFn: () =>
      apiGet<TopUser[]>("/admin/usage/top-users", { days, limit: 5 }),
    placeholderData: keepPreviousData,
  });

export const useDocumentStatus = () =>
  useQuery({
    queryKey: ["admin", "documents-status"],
    queryFn: () => apiGet<StatusCount[]>("/admin/documents/status"),
  });

export const useAdminUsers = (params: Params) =>
  useQuery({
    queryKey: ["admin", "users", params], // every filter is part of the key
    queryFn: () => apiGet<Page<AdminUser>>("/admin/users", params),
    placeholderData: keepPreviousData, // keep the old rows while new ones load
  });
```

| **Detail** | **Why** |
|---|---|
| `queryKey` contains every input (`["admin", "usage", days]`) | The key is the cache address. Change `days` and Query fetches (or reuses) that range. Forget a parameter and two screens share the wrong data |
| `placeholderData: keepPreviousData` | When the filter changes, keep showing the old rows (dimmed) until the new ones arrive, instead of flashing a skeleton |
| `refetchInterval: 60_000` on the overview | The headline numbers update themselves every minute; the heavier charts do not |
| `staleTime` | How long cached data counts as fresh. `useMe` uses a minute: who you are rarely changes |
| Retry only server errors | In `Providers`: retrying a `401` or `403` cannot help, retrying a `500` might |

**typescript  src/components/Providers.tsx**

```typescript
"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";

import { ApiError } from "@/lib/api";

export function Providers({ children }: { children: ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 30_000,
            // Retrying a 401 or 403 cannot help; retrying a 500 might.
            retry: (count, error) =>
              !(error instanceof ApiError && error.status < 500) && count < 2,
          },
        },
      }),
  );
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
```


## Tables, Filters and the URL › Putting it together: the users table

**typescript  src/components/UsersTable.tsx**

```typescript
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
```

Read it from the top. The first lines read the state **from the URL**, not from `useState`. Only the search box has local state, because typing must feel instant: the text appears at once, and an effect updates the URL 300 ms after the last keystroke (the cleanup function cancels the pending update whenever you type again, which is the whole debounce). The `filters` object is passed both to the table query and to the CSV export, which is how the export matches the screen. Finally the **Export CSV** button is inside `<RoleGate permission="export_users">`, so support staff never see it.

> **Make impossible states impossible**
>
> The component has exactly four outcomes: error, loading, data, empty (inside `DataTable`). There is no branch in which `query.data` is used before it exists, because TypeScript narrows the type for you after `isPending` and `isError`. Prefer code shaped like that over `data?.results ?? []` sprinkled everywhere.


## Testing a Dashboard

A dashboard fails in quiet ways: a number that is slightly wrong, a table that shows page 2 twice, a button that a role should not see. Three kinds of test catch them, each on the layer where the bug would live:

| **Layer** | **Tool** | **Proves** | **Example in this chapter** |
|---|---|---|---|
| Backend rules | Django test runner | Permissions, numbers, filters, query counts, CSV safety | The role matrix; `tokens_30d` ignores old usage; export defuses `=HYPERLINK` |
| Frontend behaviour | Vitest + Testing Library, with a fake `fetch` | What a person sees and what a click does, with the network faked | Sorting changes the URL; support never sees Export |
| The contract between them | The same Vitest tests, against a real server | TypeScript types and the API still agree | `LIVE_API=1 npm test` |


### Backend tests

The first file is the permission matrix and the analytics and table rules. Read the test names as a specification:

**python  api/tests/test_admin_api.py**

```python
import csv
import io
from datetime import timedelta

from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.models import User
from chat.models import Conversation, Document, UsageRecord

BASE = "/api/v1"
FAST = ["django.contrib.auth.hashers.MD5PasswordHasher"]

def put_at(queryset, **delta):
    """created_at is auto_now_add, so move rows in time with update()."""
    queryset.update(created_at=timezone.now() - timedelta(**delta))

@override_settings(PASSWORD_HASHERS=FAST)
class AdminApiTestCase(APITestCase):
    def setUp(self):
        cache.clear()
        make = User.objects.create_user
        self.admin = make("root", "root@example.com", "pw-1", role="admin")
        self.support = make("sam", "sam@example.com", "pw-1", role="support")
        self.ada = make("ada", "ada@example.com", "pw-1")

    def as_user(self, user):
        reply = self.client.post(f"{BASE}/auth/login",
                                 {"username": user.username, "password": "pw-1"})
        token = reply.data["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

class RoleTests(AdminApiTestCase):
    ANALYTICS = ["/admin/overview", "/admin/usage", "/admin/usage/top-users",
                 "/admin/documents/status"]

    def statuses(self, paths):
        return [self.client.get(BASE + p).status_code for p in paths]

    def test_members_are_locked_out_of_everything(self):
        self.as_user(self.ada)
        paths = self.ANALYTICS + ["/admin/users", "/admin/users/export"]
        self.assertEqual(set(self.statuses(paths)), {403})
        error = self.client.get(f"{BASE}/admin/users").json()["error"]
        self.assertEqual(error["code"], "permission_denied")

    def test_support_can_see_users_but_nothing_else(self):
        self.as_user(self.support)
        self.assertEqual(self.client.get(f"{BASE}/admin/users").status_code, 200)
        self.assertEqual(set(self.statuses(self.ANALYTICS)), {403})
        export = self.client.get(f"{BASE}/admin/users/export")
        self.assertEqual(export.status_code, 403)

    def test_admins_can_do_everything(self):
        self.as_user(self.admin)
        paths = self.ANALYTICS + ["/admin/users", "/admin/users/export"]
        self.assertEqual(set(self.statuses(paths)), {200})

    def test_anonymous_callers_get_401(self):
        self.assertEqual(self.client.get(f"{BASE}/admin/users").status_code, 401)

    def test_me_tells_the_ui_the_role_and_permissions(self):
        self.as_user(self.support)
        me = self.client.get(f"{BASE}/me").json()
        self.assertEqual(me["role"], "support")
        self.assertEqual(me["permissions"], ["view_users"])
        self.as_user(self.admin)
        me = self.client.get(f"{BASE}/me").json()
        self.assertIn("view_analytics", me["permissions"])

    def test_logging_in_records_the_last_login(self):
        self.assertIsNone(self.ada.last_login)
        self.as_user(self.ada)
        self.ada.refresh_from_db()
        self.assertIsNotNone(self.ada.last_login)

    def test_a_role_cannot_be_changed_through_the_api(self):
        self.as_user(self.ada)
        reply = self.client.patch(f"{BASE}/me", {"role": "admin"})
        self.assertEqual(reply.status_code, 405)
        self.ada.refresh_from_db()
        self.assertEqual(self.ada.role, "member")

class AnalyticsTests(AdminApiTestCase):
    def setUp(self):
        super().setUp()
        self.as_user(self.admin)

    def test_usage_series_has_one_point_for_every_day_even_empty_ones(self):
        record = UsageRecord.objects.create(user=self.ada, input_tokens=100,
                                            output_tokens=40)
        put_at(UsageRecord.objects.filter(pk=record.pk), days=2)
        UsageRecord.objects.create(user=self.ada, input_tokens=10,
                                   output_tokens=5)
        data = self.client.get(f"{BASE}/admin/usage?days=7").json()
        series = data["series"]
        self.assertEqual((data["days"], len(series)), (7, 7))
        dates = [point["date"] for point in series]
        self.assertEqual(dates, sorted(dates))                 # oldest first
        self.assertEqual(dates[-1], str(timezone.localdate()))
        by_date = {p["date"]: p for p in series}
        day_before_yesterday = str(timezone.localdate() - timedelta(days=2))
        self.assertEqual(by_date[day_before_yesterday]["input_tokens"], 100)
        self.assertEqual(sum(p["calls"] for p in series), 2)
        self.assertEqual(series[0]["calls"], 0)                # a gap, filled

    def test_bad_days_is_a_field_error(self):
        for bad in ("0", "400", "abc"):
            reply = self.client.get(f"{BASE}/admin/usage?days={bad}")
            self.assertEqual(reply.status_code, 400)
            self.assertIn("days", reply.json()["error"]["fields"])

    def test_overview_counts(self):
        chat = Conversation.objects.create(user=self.ada, title="x")
        UsageRecord.objects.create(user=self.ada, input_tokens=300,
                                   output_tokens=200)
        Document.objects.create(user=self.ada, filename="a.pdf")
        data = self.client.get(f"{BASE}/admin/overview").json()
        self.assertEqual((data["users_total"], data["users_new_7d"]), (3, 3))
        self.assertEqual(data["tokens_today"], 500)
        self.assertEqual(data["documents_total"], 1)
        self.assertTrue(chat.pk)

    def test_top_users_ranks_by_tokens(self):
        UsageRecord.objects.create(user=self.ada, input_tokens=900,
                                   output_tokens=0)
        UsageRecord.objects.create(user=self.support, input_tokens=100,
                                   output_tokens=0)
        rows = self.client.get(f"{BASE}/admin/usage/top-users?limit=1").json()
        self.assertEqual(rows, [{"username": "ada", "tokens": 900}])

    def test_document_status_lists_every_status_even_with_zero(self):
        Document.objects.create(user=self.ada, filename="a.pdf", status="ready")
        rows = self.client.get(f"{BASE}/admin/documents/status").json()
        self.assertEqual({r["status"]: r["count"] for r in rows},
                         {"uploaded": 0, "processing": 0, "ready": 1,
                          "failed": 0})

class UserTableTests(AdminApiTestCase):
    def setUp(self):
        super().setUp()
        for n in range(25):
            User.objects.create_user(f"user{n:02d}", f"u{n:02d}@example.com",
                                     "pw-1")
        self.as_user(self.admin)

    def test_pages_have_a_count_and_stable_content(self):
        first = self.client.get(f"{BASE}/admin/users?page_size=10").json()
        self.assertEqual((first["count"], len(first["results"])), (28, 10))
        seen = []
        url = f"{BASE}/admin/users?page_size=10&ordering=role"     # many ties
        while url:
            page = self.client.get(url).json()
            seen += [u["id"] for u in page["results"]]
            url = page["next"]
        self.assertEqual((len(seen), len(set(seen))), (28, 28))

    def test_the_list_costs_three_queries_however_long_it_is(self):
        with self.assertNumQueries(3):                 # the caller, count, page
            self.client.get(f"{BASE}/admin/users?page_size=25")

    def test_filters_search_and_ordering_whitelist(self):
        by_role = self.client.get(f"{BASE}/admin/users?role=support").json()
        self.assertEqual([u["username"] for u in by_role["results"]], ["sam"])
        found = self.client.get(f"{BASE}/admin/users?search=user07").json()
        self.assertEqual([u["username"] for u in found["results"]], ["user07"])
        self.ada.is_active = False
        self.ada.save()
        inactive = self.client.get(f"{BASE}/admin/users?is_active=false").json()
        self.assertEqual([u["username"] for u in inactive["results"]], ["ada"])
        ordered = self.client.get(f"{BASE}/admin/users?ordering=username").json()
        names = [u["username"] for u in ordered["results"]]
        self.assertEqual(names, sorted(names))
        odd = self.client.get(f"{BASE}/admin/users?ordering=password")
        self.assertEqual(odd.status_code, 200)             # ignored, not obeyed

    def test_the_numbers_per_user_are_right(self):
        Conversation.objects.create(user=self.ada, title="kept")
        Conversation.objects.create(user=self.ada, title="gone",
                                    deleted_at=timezone.now())
        recent = UsageRecord.objects.create(user=self.ada, input_tokens=100,
                                            output_tokens=50)
        old = UsageRecord.objects.create(user=self.ada, input_tokens=9000,
                                         output_tokens=0)
        put_at(UsageRecord.objects.filter(pk=old.pk), days=45)      # too old
        found = self.client.get(f"{BASE}/admin/users?search=ada").json()
        row = found["results"][0]
        self.assertEqual(row["conversation_count"], 1)      # not the deleted one
        self.assertEqual(row["tokens_30d"], 150)                    # not 9,150
        self.assertTrue(recent.pk)

    def test_the_password_hash_is_never_in_the_response(self):
        found = self.client.get(f"{BASE}/admin/users?search=ada").json()
        row = found["results"][0]
        self.assertNotIn("password", row)
        self.assertEqual(sorted(row), sorted(
            ["id", "username", "email", "role", "is_active", "date_joined",
             "last_login", "conversation_count", "tokens_30d"]))

class CsvExportTests(AdminApiTestCase):
    def rows(self, query=""):
        reply = self.client.get(f"{BASE}/admin/users/export{query}")
        self.assertEqual(reply.status_code, 200)
        self.assertEqual(reply["Content-Type"], "text/csv")
        self.assertIn("attachment", reply["Content-Disposition"])
        text = b"".join(reply.streaming_content).decode()
        return list(csv.DictReader(io.StringIO(text)))

    def test_export_follows_the_same_filters_as_the_table(self):
        self.as_user(self.admin)
        rows = self.rows("?role=support")
        self.assertEqual([r["username"] for r in rows], ["sam"])

    def test_spreadsheet_formulas_are_defused(self):
        evil = '=HYPERLINK("http://evil")'
        User.objects.create_user(evil, "x@example.com", "pw-1")
        self.as_user(self.admin)
        names = [r["username"] for r in self.rows()]
        self.assertIn("'=HYPERLINK(\"http://evil\")", names)
        self.assertFalse(any(n.startswith("=") for n in names))

    def test_exports_are_rate_limited(self):
        self.as_user(self.admin)
        codes = [self.client.get(f"{BASE}/admin/users/export").status_code
                 for _ in range(6)]
        self.assertEqual(codes, [200, 200, 200, 200, 200, 429])
```

**python  api/tests/test_django_admin.py**

```python
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from chat.models import Conversation, Document

FAST = ["django.contrib.auth.hashers.MD5PasswordHasher"]

@override_settings(PASSWORD_HASHERS=FAST)
class DjangoAdminTests(TestCase):
    def setUp(self):
        self.boss = User.objects.create_superuser("boss", "b@example.com", "pw-1")
        self.client.force_login(self.boss)
        self.ada = User.objects.create_user("ada", "a@example.com", "pw-1")

    def test_every_list_page_loads(self):
        for model in ("accounts_user", "chat_conversation", "chat_message",
                      "chat_document"):
            reply = self.client.get(reverse(f"admin:{model}_changelist"))
            self.assertEqual(reply.status_code, 200, model)

    def test_restore_action_undeletes_conversations(self):
        chat = Conversation.objects.create(user=self.ada, title="x",
                                           deleted_at=timezone.now())
        self.client.post(reverse("admin:chat_conversation_changelist"), {
            "action": "restore_conversations", "_selected_action": [chat.pk]})
        chat.refresh_from_db()
        self.assertIsNone(chat.deleted_at)

    def test_reprocess_action_queues_documents(self):
        doc = Document.objects.create(user=self.ada, filename="a.pdf",
                                      status="failed", error="boom")
        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            self.client.post(reverse("admin:chat_document_changelist"), {
                "action": "reprocess", "_selected_action": [doc.pk]})
        doc.refresh_from_db()
        self.assertEqual((doc.status, doc.error, len(callbacks)),
                         ("processing", "", 1))

    def test_ordinary_members_cannot_enter_the_admin(self):
        self.client.force_login(self.ada)
        reply = self.client.get(reverse("admin:index"))
        self.assertEqual(reply.status_code, 302)               # sent to log in
```


### Frontend tests

Component tests need three small pieces of infrastructure: a config that gives Vitest a browser-like environment, a setup file, and helpers that fake the network and the signed-in user:

**typescript  vitest.config.mts**

```typescript
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    globals: true,
  },
});
```

**typescript  src/test/setup.ts**

```typescript
import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

afterEach(cleanup);
```

**typescript  src/test/helpers.tsx**

```typescript
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { vi } from "vitest";

import type { AdminUser, Me, Role } from "@/lib/types";

export const PERMISSIONS: Record<Role, Me["permissions"]> = {
  member: [],
  support: ["view_users"],
  admin: ["view_users", "export_users", "view_analytics"],
};

export const meFor = (role: Role): Me => ({
  id: "1",
  username: role,
  email: `${role}@example.com`,
  role,
  permissions: PERMISSIONS[role],
  date_joined: "2026-01-01T00:00:00Z",
});

export const user = (n: number): AdminUser => ({
  id: String(n),
  username: `user${n}`,
  email: `user${n}@example.com`,
  role: "member",
  is_active: true,
  date_joined: "2026-10-01T09:00:00Z",
  last_login: null,
  conversation_count: n,
  tokens_30d: n * 1000,
});

/** Answer fetch() by URL, like a tiny fake server. */
export function fakeApi(routes: Record<string, (url: URL) => unknown>) {
  const calls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: string) => {
      const url = new URL(input);
      calls.push(url.pathname + url.search);
      const handler = routes[url.pathname];
      if (!handler) return new Response("{}", { status: 404 });
      return new Response(JSON.stringify(handler(url)), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }),
  );
  return calls;
}

/** `seed` pre-fills the cache (e.g. who is signed in) so tests need not wait. */
export function renderWithClient(
  ui: ReactElement,
  seed?: (client: QueryClient) => void,
) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  seed?.(client);
  return render(
    <QueryClientProvider client={client}>{ui}</QueryClientProvider>,
  );
}
```

- `fakeApi` replaces `fetch` with a tiny fake server that answers by path and records every call. A test can then assert both what the screen shows and exactly which URL was requested.
- `renderWithClient(ui, seed)` wraps a component in a fresh `QueryClient` (with retries off, so failures show up instantly). The optional `seed` pre-fills the cache with "who is signed in", so a role test does not have to wait for a network call.
- **Tests find elements the way a person does:** by role and accessible name (`getByRole("button", { name: "Export CSV" })`), not by class names. If the accessible name breaks, the test breaks, and so would a screen reader.
**typescript  src/lib/permissions.test.ts**

```typescript
import { describe, expect, it } from "vitest";

import { meFor } from "@/test/helpers";
import { can, homeFor, visibleNav } from "./permissions";

describe("permissions", () => {
  it("answers from the permission list, never from the role name", () => {
    expect(can(meFor("admin"), "export_users")).toBe(true);
    expect(can(meFor("support"), "export_users")).toBe(false);
    expect(can(undefined, "view_users")).toBe(false); // not loaded yet
  });

  it("shows each role only the menu items it may open", () => {
    expect(visibleNav(meFor("admin")).map((i) => i.label)).toEqual([
      "Overview",
      "Users",
    ]);
    expect(visibleNav(meFor("support")).map((i) => i.label)).toEqual(["Users"]);
    expect(visibleNav(meFor("member"))).toEqual([]);
  });

  it("sends people to the first page they may open", () => {
    expect(homeFor(meFor("admin"))).toBe("/admin");
    expect(homeFor(meFor("support"))).toBe("/admin/users");
    expect(homeFor(meFor("member"))).toBeNull();
  });
});
```

**typescript  src/lib/format.test.ts**

```typescript
import { describe, expect, it } from "vitest";

import { formatCompact, formatDay, formatNumber } from "./format";

describe("format", () => {
  it("shortens big numbers for axes and spells them out for tables", () => {
    expect(formatCompact(12400)).toBe("12.4K");
    expect(formatNumber(12400)).toBe("12,400");
  });

  it("shows a calendar day as that same day in every time zone", () => {
    expect(formatDay("2026-11-03")).toBe("Nov 3");
    expect(formatDay("2026-01-01")).toBe("Jan 1");
  });
});
```

**typescript  src/lib/api.test.ts**

```typescript
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, apiGet, buildQuery } from "./api";
import { setAccessToken } from "./auth";

afterEach(() => {
  vi.unstubAllGlobals();
  setAccessToken(null);
});

describe("buildQuery", () => {
  it("leaves out empty values so URLs stay clean", () => {
    expect(buildQuery({ page: 2, search: "", role: null, x: undefined })).toBe(
      "?page=2",
    );
    expect(buildQuery({})).toBe("");
    expect(buildQuery({ q: "a b&c" })).toBe("?q=a+b%26c"); // encoded safely
  });
});

describe("apiGet", () => {
  it("sends the token and parses the JSON", async () => {
    setAccessToken("abc");
    const fetchMock = vi.fn(
      async () => new Response('{"ok":true}', { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchMock);
    expect(await apiGet("/me")).toEqual({ ok: true });
    const [url, init] = fetchMock.mock.calls[0] as unknown as [
      string,
      RequestInit,
    ];
    expect(url).toBe("http://localhost:8000/api/v1/me");
    expect((init.headers as Record<string, string>).Authorization).toBe(
      "Bearer abc",
    );
  });

  it("turns the API's error shape into an ApiError", async () => {
    const body = { error: { code: "permission_denied", message: "No." } };
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify(body), { status: 403 })),
    );
    await expect(apiGet("/admin/users")).rejects.toMatchObject({
      status: 403,
      code: "permission_denied",
      message: "No.",
    });
    await expect(apiGet("/admin/users")).rejects.toBeInstanceOf(ApiError);
  });
});
```

**typescript  src/components/RoleGate.test.tsx**

```typescript
import { screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { fakeApi, meFor, renderWithClient } from "@/test/helpers";
import { RequirePermission, RoleGate } from "./RoleGate";
import type { Role } from "@/lib/types";

afterEach(() => vi.unstubAllGlobals());

function signedInAs(role: Role) {
  return fakeApi({ "/api/v1/me": () => meFor(role) });
}

describe("RoleGate", () => {
  it("shows the button to an admin", async () => {
    signedInAs("admin");
    renderWithClient(
      <RoleGate permission="export_users">
        <button>Export</button>
      </RoleGate>,
    );
    expect(
      await screen.findByRole("button", { name: "Export" }),
    ).toBeInTheDocument();
  });

  it("hides the button from support staff and shows the fallback", async () => {
    const calls = signedInAs("support");
    renderWithClient(
      <RoleGate permission="export_users" fallback={<span>read-only</span>}>
        <button>Export</button>
      </RoleGate>,
    );
    expect(await screen.findByText("read-only")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Export" })).toBeNull();
    expect(calls).toEqual(["/api/v1/me"]);
  });
});

describe("RequirePermission", () => {
  it("never mounts a page for the wrong role (so no fetch)", async () => {
    const mounted = vi.fn();
    function Page() {
      mounted();
      return <p>secret numbers</p>;
    }
    signedInAs("support");
    renderWithClient(
      <RequirePermission permission="view_analytics">
        <Page />
      </RequirePermission>,
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "do not have access",
    );
    expect(mounted).not.toHaveBeenCalled();
    const link = screen.getByRole("link"); // a way out
    expect(link).toHaveAttribute("href", "/admin/users");
  });

  it("renders the page for the right role", async () => {
    signedInAs("admin");
    renderWithClient(
      <RequirePermission permission="view_analytics">
        <p>numbers</p>
      </RequirePermission>,
    );
    expect(await screen.findByText("numbers")).toBeInTheDocument();
  });
});
```

**typescript  src/components/ChartCard.test.tsx**

```typescript
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ChartCard } from "./dashboard/ChartCard";

const table = {
  caption: "Tokens per day",
  headers: ["Day", "Tokens"],
  rows: [
    ["Nov 2", 100],
    ["Nov 3", 250],
  ],
};

describe("ChartCard", () => {
  it("shows a loading placeholder, not a blank hole", () => {
    render(<ChartCard title="AI usage" state="loading" />);
    expect(
      screen.getByRole("status", { name: "Loading AI usage" }),
    ).toBeInTheDocument();
  });

  it("offers a retry when the request failed", async () => {
    const retry = vi.fn();
    render(<ChartCard title="AI usage" state="error" onRetry={retry} />);
    expect(screen.getByRole("alert")).toHaveTextContent("could not load");
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(retry).toHaveBeenCalledOnce();
  });

  it("says plainly when there is no data", () => {
    render(<ChartCard title="AI usage" state="empty" />);
    expect(screen.getByText(/No data for this period/)).toBeInTheDocument();
  });

  it("gives screen-reader users the same numbers as a table", () => {
    render(
      <ChartCard
        title="AI usage"
        description="Tokens per day"
        state="ready"
        table={table}
      >
        <svg />
      </ChartCard>,
    );
    expect(screen.getByRole("img", { name: /AI usage/ })).toBeInTheDocument();
    const grid = screen.getByRole("table", { name: "Tokens per day" });
    expect(grid).toHaveClass("sr-only"); // invisible, but read aloud
    expect(screen.getByRole("cell", { name: "250" })).toBeInTheDocument();
  });
});
```

**typescript  src/components/UsersTable.test.tsx**

```typescript
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Role } from "@/lib/types";
import { fakeApi, meFor, renderWithClient, user } from "@/test/helpers";
import { UsersTable } from "./UsersTable";

const nav = vi.hoisted(() => ({
  replace: vi.fn(),
  params: new URLSearchParams(),
}));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: nav.replace }),
  usePathname: () => "/admin/users",
  useSearchParams: () => nav.params,
}));

/** 45 users in total, served 20 at a time like the real API. */
const usersPage = (url: URL) => {
  const start = (Number(url.searchParams.get("page") ?? 1) - 1) * 20;
  const size = Math.max(Math.min(20, 45 - start), 0);
  return {
    count: 45,
    next: null,
    previous: null,
    results: Array.from({ length: size }, (_, i) => user(start + i + 1)),
  };
};

const show = (role: Role = "admin") =>
  renderWithClient(<UsersTable />, (c) => c.setQueryData(["me"], meFor(role)));

beforeEach(() => {
  nav.replace.mockClear();
  nav.params = new URLSearchParams();
});
afterEach(() => vi.unstubAllGlobals());

describe("UsersTable", () => {
  it("shows the rows and the total from the API", async () => {
    fakeApi({ "/api/v1/admin/users": usersPage });
    show();
    expect(await screen.findByText("user1")).toBeInTheDocument();
    expect(screen.getByText("Showing 1–20 of 45")).toBeInTheDocument();
    expect(screen.getAllByRole("row")).toHaveLength(21); // header + 20
  });

  it("asks the API for exactly what the URL says", async () => {
    nav.params = new URLSearchParams(
      "q=sam&role=support&page=2&ordering=-tokens_30d",
    );
    const calls = fakeApi({ "/api/v1/admin/users": usersPage });
    show();
    await screen.findByText("user21");
    expect(calls).toContain(
      "/api/v1/admin/users?search=sam&role=support" +
        "&ordering=-tokens_30d&page=2&page_size=20",
    );
  });

  it("sorts on the server: a header click only changes the URL", async () => {
    fakeApi({ "/api/v1/admin/users": usersPage });
    show();
    await userEvent.click(await screen.findByRole("button", { name: /User/ }));
    expect(nav.replace).toHaveBeenCalledWith("/admin/users?ordering=username", {
      scroll: false,
    });
  });

  it("marks the sorted column for assistive technology", async () => {
    nav.params = new URLSearchParams("ordering=-tokens_30d");
    fakeApi({ "/api/v1/admin/users": usersPage });
    show();
    const header = await screen.findByRole("columnheader", { name: /Tokens/ });
    expect(header).toHaveAttribute("aria-sort", "descending");
  });

  it("moves between pages through the URL", async () => {
    fakeApi({ "/api/v1/admin/users": usersPage });
    show();
    await userEvent.click(await screen.findByRole("button", { name: "Next" }));
    expect(nav.replace).toHaveBeenCalledWith("/admin/users?page=2", {
      scroll: false,
    });
  });

  it("goes back to page 1 when a filter changes", async () => {
    nav.params = new URLSearchParams("page=3");
    fakeApi({ "/api/v1/admin/users": usersPage });
    show();
    await userEvent.selectOptions(
      await screen.findByLabelText("Role"),
      "support",
    );
    expect(nav.replace).toHaveBeenCalledWith("/admin/users?role=support", {
      scroll: false,
    });
  });

  it("waits for the typing to pause before changing the URL", async () => {
    fakeApi({ "/api/v1/admin/users": usersPage });
    show();
    await userEvent.type(await screen.findByRole("searchbox"), "ada");
    expect(nav.replace).not.toHaveBeenCalled(); // still typing
    await waitFor(
      () =>
        expect(nav.replace).toHaveBeenCalledWith("/admin/users?q=ada", {
          scroll: false,
        }),
      { timeout: 1500 },
    );
    expect(nav.replace).toHaveBeenCalledTimes(1); // one change, not three
  });

  it("offers the export to admins only", async () => {
    fakeApi({ "/api/v1/admin/users": usersPage });
    const { unmount } = show("admin");
    await screen.findByText("user1");
    expect(
      screen.getByRole("button", { name: "Export CSV" }),
    ).toBeInTheDocument();
    unmount();
    show("support");
    await screen.findByText("user1");
    expect(screen.queryByRole("button", { name: "Export CSV" })).toBeNull();
  });

  it("explains an empty result", async () => {
    fakeApi({
      "/api/v1/admin/users": () => ({
        count: 0,
        next: null,
        previous: null,
        results: [],
      }),
    });
    show();
    expect(
      await screen.findByText("No users match these filters."),
    ).toBeInTheDocument();
    expect(screen.getByText("Showing 0–0 of 0")).toBeInTheDocument();
  });

  it("shows an error with a retry instead of a broken table", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("{}", { status: 500 })),
    );
    show();
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "could not load the users",
    );
    expect(
      screen.getByRole("button", { name: "Try again" }),
    ).toBeInTheDocument();
  });
});
```

Two things to notice in the table test. It mocks `next/navigation`, so "the URL" is a variable the test controls, and the assertion `expect(nav.replace).toHaveBeenCalledTimes(1)` after typing `ada` is what proves the debounce: three keystrokes, one URL change. And the test for the export button renders the component twice, once as admin and once as support, in the same test, because the interesting fact is the **difference**.

> **What jsdom cannot test**
>
> Charts are drawn in SVG from measured pixel sizes, and jsdom has no layout, so the Recharts drawing itself is not tested here. That is why the chart code is kept thin: the data preparation lives in the API (tested in Django), the states live in `ChartCard` (tested above), and what remains is configuration. For pixel-level checks, add a browser test with Playwright (Chapter 42).


### A test against the real server

Mocks prove your components handle the shapes you *believe* the API returns. The next file proves the belief is true. It is skipped unless you set `LIVE_API=1`, then signs in as the demo users and calls the real endpoints through the same `apiGet` the dashboard uses:

**typescript  src/test/live.test.ts**

```typescript
// Runs only against a real server:  LIVE_API=1 npm test
// It proves the TypeScript types and the Django API still agree.
import { beforeEach, describe, expect, it } from "vitest";

import { ApiError, apiGet, apiPost } from "@/lib/api";
import { setAccessToken } from "@/lib/auth";
import type { AdminUser, Me, Overview, Page, UsageSeries } from "@/lib/types";

async function signIn(username: string) {
  const tokens = await apiPost<{ access: string }>("/auth/login", {
    username,
    password: "demo-pass-1",
  });
  setAccessToken(tokens.access);
}

const keys = (value: object) => Object.keys(value).sort();

describe.skipIf(!process.env.LIVE_API)("against the real Django API", () => {
  beforeEach(() => setAccessToken(null));

  it("gives an admin every shape the types promise", async () => {
    await signIn("demo_admin");
    const me = await apiGet<Me>("/me");
    expect(me.permissions).toEqual([
      "view_users",
      "export_users",
      "view_analytics",
    ]);

    const overview = await apiGet<Overview>("/admin/overview");
    expect(keys(overview)).toEqual([
      "documents_total",
      "messages_today",
      "tokens_today",
      "users_new_7d",
      "users_total",
    ]);

    const usage = await apiGet<UsageSeries>("/admin/usage", { days: 30 });
    expect(usage.series).toHaveLength(30); // no gaps
    expect(keys(usage.series[0])).toEqual([
      "calls",
      "date",
      "input_tokens",
      "output_tokens",
    ]);

    const page = await apiGet<Page<AdminUser>>("/admin/users", {
      page_size: 5,
      ordering: "-tokens_30d",
    });
    expect(page.count).toBe(42);
    expect(page.results).toHaveLength(5);
    const tokens = page.results.map((u) => u.tokens_30d);
    const sorted = [...tokens].sort((a, b) => b - a); // sorted by the server
    expect(tokens).toEqual(sorted);
    expect(keys(page.results[0])).toEqual([
      "conversation_count",
      "date_joined",
      "email",
      "id",
      "is_active",
      "last_login",
      "role",
      "tokens_30d",
      "username",
    ]);
  });

  it("lets support read users but refuses analytics", async () => {
    await signIn("demo_support");
    expect((await apiGet<Page<AdminUser>>("/admin/users")).count).toBe(42);
    await expect(apiGet("/admin/overview")).rejects.toMatchObject({
      status: 403,
      code: "permission_denied",
    });
    await expect(apiGet("/admin/users/export")).rejects.toBeInstanceOf(
      ApiError,
    );
  });

  it("refuses members everywhere, and anonymous callers with 401", async () => {
    await signIn("demo_user00");
    await expect(apiGet("/admin/users")).rejects.toMatchObject({ status: 403 });
    setAccessToken(null);
    await expect(apiGet("/me")).rejects.toMatchObject({
      status: 401,
      code: "not_authenticated",
    });
  });

  it("filters on the server", async () => {
    await signIn("demo_admin");
    const staff = await apiGet<Page<AdminUser>>("/admin/users", {
      role: "support",
    });
    expect(staff.results.map((u) => u.username)).toEqual(["demo_support"]);
    const none = await apiGet<Page<AdminUser>>("/admin/users", {
      search: "zzz-nobody",
    });
    expect(none).toMatchObject({ count: 0, results: [] });
  });
});
```


## Reference Listings

These are the remaining files from the project, collected so every file in the chapter can be copied from the page. They contain no new ideas.


### Backend

**python  api/v1/urls.py**

```python
from django.urls import include, path
from rest_framework.routers import SimpleRouter

from . import admin_views, views

router = SimpleRouter(trailing_slash=False)
router.register("conversations", views.ConversationViewSet,
                basename="conversation")
router.register("documents", views.DocumentViewSet, basename="document")
router.register("admin/users", admin_views.AdminUserViewSet,
                basename="admin-user")

urlpatterns = [
    path("auth/login", views.LoginView.as_view(), name="login"),
    path("auth/refresh", views.RefreshView.as_view(), name="refresh"),
    path("auth/logout", views.LogoutView.as_view(), name="logout"),
    path("me", views.MeView.as_view(), name="me"),
    path("me/usage", views.UsageView.as_view(), name="usage"),
    path("admin/overview", admin_views.OverviewView.as_view()),
    path("admin/usage", admin_views.UsageSeriesView.as_view()),
    path("admin/usage/top-users", admin_views.TopUsersView.as_view()),
    path("admin/documents/status", admin_views.DocumentStatusView.as_view()),
    path("meta/client-config", views.ClientConfigView.as_view()),
    path("health", views.HealthView.as_view()),
    path(
        "conversations/<uuid:conversation_id>/messages",
        views.MessageViewSet.as_view({"get": "list", "post": "create"}),
        name="messages",
    ),
    path("", include(router.urls)),
]
```

**python  config/settings.py (changed and added settings)**

```python
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=30),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,           # otherwise "last login" stays empty
}

SPECTACULAR_SETTINGS = {
    "TITLE": "AI Chat API",
    "DESCRIPTION": "REST API for the AI Chat SaaS (all paths under /api/v1).",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "ENUM_NAME_OVERRIDES": {                 # two models both have a "role"
        "UserRoleEnum": "accounts.models.User.Role",
        "MessageRoleEnum": "chat.models.Message.Role",
    },
}
```

**python  config/settings.py (the throttle rates, with the new export scope)**

```python
"DEFAULT_THROTTLE_RATES": {
    "anon": "30/min", "user": "300/min",
    "ai_chat": "20/min", "auth": "10/min", "export": "5/min",
},
```

**python  chat/management/commands/seed_demo.py**

```python
import random
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounts.models import User
from chat.models import Conversation, Document, Message, UsageRecord

class Command(BaseCommand):
    help = "Create demo users and months of usage so the dashboard has data."

    def add_arguments(self, parser):
        parser.add_argument("--users", type=int, default=40)
        parser.add_argument("--days", type=int, default=90)

    @transaction.atomic
    def handle(self, *args, **options):
        rng = random.Random(42)                   # same data for the same day
        now, days = timezone.now(), options["days"]
        User.objects.filter(username__startswith="demo_").delete()

        staff = [("demo_admin", "admin"), ("demo_support", "support")]
        for name, role in staff:
            User.objects.create_user(name, f"{name}@example.com",
                                     "demo-pass-1", role=role)
        members = [
            User.objects.create_user(
                f"demo_user{n:02d}", f"user{n:02d}@example.com", "demo-pass-1",
                date_joined=now - timedelta(days=rng.randint(0, days - 1)))
            for n in range(options["users"])
        ]

        usage, chats, docs = [], [], []
        for user in members:
            activity = rng.choice([0.2, 0.5, 0.8])         # light to heavy user
            for back in range(days - 1, -1, -1):
                day = now - timedelta(days=back)
                if day < user.date_joined:
                    continue
                busy = 0.35 if day.weekday() >= 5 else 0.75   # quieter weekends
                if rng.random() < activity * busy:
                    for _ in range(rng.randint(1, 6)):
                        usage.append(UsageRecord(
                            user=user, input_tokens=rng.randint(200, 2500),
                            output_tokens=rng.randint(100, 1800)))
                        usage[-1].when = day - timedelta(
                            minutes=rng.randint(0, 1000))
            for n in range(rng.randint(1, 4)):
                chats.append(Conversation(user=user, title=f"Chat {n + 1}"))
            for n in range(rng.choice([0, 0, 1, 2, 3])):
                docs.append(Document(
                    user=user, filename=f"file{n + 1}.pdf",
                    status=rng.choices(Document.Status.values,
                                       weights=[1, 2, 14, 3])[0]))

        UsageRecord.objects.bulk_create(usage)
        for record in usage:
            record.created_at = max(record.when, record.user.date_joined)
        UsageRecord.objects.bulk_update(usage, ["created_at"], batch_size=500)
        Conversation.objects.bulk_create(chats)
        Document.objects.bulk_create(docs)

        messages = []
        for chat in chats:
            for n in range(rng.randint(2, 6)):
                messages.append(Message(
                    conversation=chat, content=f"Message {n + 1}",
                    role="user" if n % 2 == 0 else "assistant"))
        Message.objects.bulk_create(messages)
        for message in messages:                  # spread over the period
            message.created_at = now - timedelta(
                days=rng.randint(0, days - 1), minutes=rng.randint(0, 1000))
        Message.objects.bulk_update(messages, ["created_at"], batch_size=500)
        self.stdout.write(self.style.SUCCESS(
            f"Created {len(members) + len(staff)} users, {len(chats)} "
            f"conversations, {len(messages)} messages,\n{len(usage)} usage "
            f"records and {len(docs)} documents."))
```


### Frontend

**typescript  src/lib/auth.ts**

```typescript
// A development stand-in: the token lives in memory only.
// Chapter 20 builds the real flow (refresh cookie, route protection).
// The dashboard depends on just this one function.
let accessToken: string | null = null;

export const getAccessToken = () => accessToken;
export const setAccessToken = (token: string | null) => {
  accessToken = token;
};
```

**typescript  src/lib/types.ts**

```typescript
// Written by hand here; Chapter 20 generates these from the OpenAPI file.
export type Role = "member" | "support" | "admin";
export type Permission = "view_users" | "export_users" | "view_analytics";

export interface Me {
  id: string;
  username: string;
  email: string;
  role: Role;
  permissions: Permission[];
  date_joined: string;
}

export interface Page<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface AdminUser {
  id: string;
  username: string;
  email: string;
  role: Role;
  is_active: boolean;
  date_joined: string;
  last_login: string | null;
  conversation_count: number;
  tokens_30d: number;
}

export interface Overview {
  users_total: number;
  users_new_7d: number;
  tokens_today: number;
  messages_today: number;
  documents_total: number;
}

export interface UsagePoint {
  date: string; // "2026-11-03", a calendar day, not a moment
  input_tokens: number;
  output_tokens: number;
  calls: number;
}

export interface UsageSeries {
  days: number;
  series: UsagePoint[];
}

export interface TopUser {
  username: string;
  tokens: number;
}

export interface StatusCount {
  status: string;
  count: number;
}
```

**typescript  src/lib/ui.ts**

```typescript
// Shared Tailwind classes: change a look in one place (Chapter 19).
export const ui = {
  page:
    "min-h-full bg-gray-50 text-gray-900 " +
    "dark:bg-gray-950 dark:text-gray-100",
  card:
    "rounded-xl border border-gray-200 bg-white p-4 " +
    "dark:border-gray-800 dark:bg-gray-900",
  tableWrap:
    "overflow-x-auto rounded-xl border border-gray-200 " +
    "dark:border-gray-800",
  field:
    "rounded-md border border-gray-300 bg-white px-2 py-1 text-sm " +
    "dark:border-gray-700 dark:bg-gray-900",
  primary:
    "rounded-md bg-blue-600 px-3 py-1.5 text-sm text-white " +
    "disabled:opacity-50",
  secondary:
    "rounded-md border border-gray-300 px-3 py-1 text-sm " +
    "hover:bg-gray-50 disabled:opacity-40 " +
    "dark:border-gray-700 dark:hover:bg-gray-800",
  sidebar:
    "flex w-56 shrink-0 flex-col border-r border-gray-200 p-4 " +
    "dark:border-gray-800",
  empty: "flex h-72 items-center justify-center text-sm text-gray-500",
  skeleton: "animate-pulse rounded bg-gray-100 dark:bg-gray-800",
  navCurrent:
    "bg-blue-50 font-medium text-blue-700 " +
    "dark:bg-blue-950 dark:text-blue-300",
};
```

**typescript  src/app/layout.tsx**

```typescript
import type { Metadata } from "next";
import "./globals.css";
import { Providers } from "@/components/Providers";
import { ui } from "@/lib/ui";

export const metadata: Metadata = {
  title: "AI Chat Admin",
  description: "Dashboards and admin tools for the AI Chat SaaS",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className={ui.page}>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
```

**typescript  src/app/login/page.tsx**

```typescript
"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { ApiError, apiGet, apiPost } from "@/lib/api";
import { setAccessToken } from "@/lib/auth";
import { homeFor } from "@/lib/permissions";
import type { Me } from "@/lib/types";
import { ui } from "@/lib/ui";

// A development login. Chapter 20 replaces it with the real authentication flow.
export default function LoginPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setError(null);
    try {
      const tokens = await apiPost<{ access: string }>("/auth/login", {
        username: form.get("username"),
        password: form.get("password"),
      });
      setAccessToken(tokens.access);
      const me = await queryClient.fetchQuery({
        queryKey: ["me"],
        queryFn: () => apiGet<Me>("/me"),
      });
      router.replace(homeFor(me) ?? "/admin");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  }

  const field = `${ui.field} mt-1 w-full py-2`;
  return (
    <main className={`${ui.card} mx-auto mt-24 max-w-sm p-6`}>
      <h1 className="mb-4 text-xl font-semibold">Sign in</h1>
      <form onSubmit={submit} className="space-y-3">
        <label className="block text-sm">
          Username
          <input
            name="username"
            required
            autoComplete="username"
            className={field}
          />
        </label>
        <label className="block text-sm">
          Password
          <input
            name="password"
            type="password"
            required
            autoComplete="current-password"
            className={field}
          />
        </label>
        {error && (
          <p role="alert" className="text-sm text-red-600">
            {error}
          </p>
        )}
        <button disabled={busy} className={`${ui.primary} w-full py-2`}>
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </main>
  );
}
```

**css  src/app/globals.css**

```css
@import "tailwindcss";

body {
  font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
}
```

**typescript  src/app/page.tsx**

```typescript
import { redirect } from "next/navigation";

export default function Home() {
  redirect("/admin");
}
```
