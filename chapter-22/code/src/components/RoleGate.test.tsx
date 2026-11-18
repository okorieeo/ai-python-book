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
