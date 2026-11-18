import type { Me, Permission } from "./types";

/** The UI asks "may I?", never "am I an admin?". The API decides the answer. */
export function can(me: Me | undefined, permission: Permission): boolean {
  return !!me && me.permissions.includes(permission);
}

export interface NavItem {
  href: string;
  label: string;
  permission: Permission;
}

export const NAV_ITEMS: NavItem[] = [
  { href: "/admin", label: "Overview", permission: "view_analytics" },
  { href: "/admin/users", label: "Users", permission: "view_users" },
];

export const visibleNav = (me: Me | undefined) =>
  NAV_ITEMS.filter((item) => can(me, item.permission));

/** The first page this person may open, or null if they have none. */
export const homeFor = (me: Me | undefined) => visibleNav(me)[0]?.href ?? null;
