// Rules for what we accept from a push notification. A notification is INPUT, like
// a form field: whoever can send one can put anything in it.

export function isExpoPushToken(value: unknown): value is string {
  return typeof value === "string" && /^(Expo|Exponent)PushToken\[[A-Za-z0-9_-]+\]$/.test(value);
}

// Screens a notification may open. Anything else is ignored.
const ALLOWED_ROUTES = [/^\/inbox$/, /^\/documents$/, /^\/profile$/];

/** Returns a safe in-app route from a notification payload, or null. */
export function routeFromNotificationData(data: unknown): string | null {
  if (typeof data !== "object" || data === null) return null;
  const url = (data as Record<string, unknown>).url;
  if (typeof url !== "string") return null;
  return ALLOWED_ROUTES.some((pattern) => pattern.test(url)) ? url : null;
}
