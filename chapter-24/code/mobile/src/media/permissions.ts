// Every permission has three states, and each needs a different screen:
//   granted  go ahead
//   denied   ask again, in a moment that makes sense, with a reason
//   blocked  the system will not show its dialog again: send the person to Settings

export interface PermissionLike {
  granted: boolean;
  canAskAgain: boolean;
}

export type PermissionOutcome = "granted" | "denied" | "blocked";

export async function ensurePermission(
  get: () => Promise<PermissionLike>,
  request: () => Promise<PermissionLike>,
): Promise<PermissionOutcome> {
  const current = await get();
  if (current.granted) return "granted";
  // Android shows its dialog twice at most; after that request() returns at once
  // with nothing on screen. Do not pretend to ask: say it plainly.
  if (!current.canAskAgain) return "blocked";
  const answer = await request();
  if (answer.granted) return "granted";
  return answer.canAskAgain ? "denied" : "blocked";
}
