export const PROTECTED_PREFIXES = ["/chat", "/settings", "/billing"];
export const AUTH_PAGES = ["/login", "/signup"];
export const DEFAULT_AFTER_LOGIN = "/chat";

/**
 * Where may we send the user after logging in? Only to a path on THIS site.
 * Blocks open redirects such as ?next=https://evil.example or ?next=//evil.example.
 */
export function safeNextPath(candidate: string | null | undefined, fallback = DEFAULT_AFTER_LOGIN): string {
  if (!candidate || candidate.length > 300) return fallback;
  if (/[\u0000-\u001f\u007f\\]/.test(candidate)) return fallback; // control characters and backslashes
  if (!candidate.startsWith("/") || candidate.startsWith("//")) return fallback;
  let decoded = candidate;
  try {
    decoded = decodeURIComponent(candidate);
  } catch {
    return fallback;
  }
  if (decoded.startsWith("//") || decoded.includes("://") || /[\\\u0000-\u001f]/.test(decoded)) return fallback;
  return candidate;
}

function matchesPrefix(pathname: string, prefix: string): boolean {
  return pathname === prefix || pathname.startsWith(prefix + "/");
}

/** Pure routing rule used by proxy.ts: returns the path to redirect to, or null to continue. */
export function decideRedirect(pathname: string, search: string, hasSession: boolean): string | null {
  if (!hasSession && PROTECTED_PREFIXES.some((p) => matchesPrefix(pathname, p))) {
    return `/login?next=${encodeURIComponent(pathname + search)}`;
  }
  if (hasSession && AUTH_PAGES.some((p) => matchesPrefix(pathname, p))) {
    return DEFAULT_AFTER_LOGIN;
  }
  return null;
}
