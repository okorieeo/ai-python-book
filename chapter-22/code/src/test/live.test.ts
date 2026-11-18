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
