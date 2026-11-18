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
