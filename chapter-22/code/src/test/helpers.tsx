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
