export type Plan = "free" | "pro" | "team";
export type Feature = "chat" | "image_upload" | "export" | "team_workspace";

const DAILY_MESSAGES: Record<Plan, number> = { free: 20, pro: 500, team: 2_000 };
const FEATURES: Record<Plan, ReadonlySet<Feature>> = {
  free: new Set<Feature>(["chat"]),
  pro: new Set<Feature>(["chat", "image_upload", "export"]),
  team: new Set<Feature>(["chat", "image_upload", "export", "team_workspace"]),
};

/** The UI uses this only to decide what to SHOW. The server decides what is allowed (Chapter 17). */
export function canUse(plan: Plan, feature: Feature): boolean {
  return FEATURES[plan].has(feature);
}

export function remainingMessages(plan: Plan, usedToday: number): number {
  if (!Number.isInteger(usedToday) || usedToday < 0) throw new Error("usedToday must be a non-negative integer");
  return Math.max(0, DAILY_MESSAGES[plan] - usedToday);
}

export function nextPlan(plan: Plan): Plan | null {
  return plan === "free" ? "pro" : plan === "pro" ? "team" : null;
}
