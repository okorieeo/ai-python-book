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
