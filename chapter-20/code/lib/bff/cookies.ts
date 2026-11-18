export const ACCESS_COOKIE = "ai_access";
export const REFRESH_COOKIE = "ai_refresh";

export function parseCookies(header: string | null | undefined): Record<string, string> {
  const result: Record<string, string> = {};
  if (!header) return result;
  for (const part of header.split(";")) {
    const index = part.indexOf("=");
    if (index < 0) continue;
    const name = part.slice(0, index).trim();
    if (!name || name in result) continue; // the first occurrence wins
    try {
      result[name] = decodeURIComponent(part.slice(index + 1).trim());
    } catch {
      result[name] = part.slice(index + 1).trim();
    }
  }
  return result;
}

export type CookieOptions = { maxAgeSeconds: number; secure: boolean; path?: string };

/** An HttpOnly, SameSite=Lax cookie: JavaScript cannot read it, and other websites cannot make the browser send it on POSTs. */
export function serializeCookie(name: string, value: string, options: CookieOptions): string {
  const parts = [
    `${name}=${encodeURIComponent(value)}`,
    `Path=${options.path ?? "/"}`,
    `Max-Age=${Math.max(0, Math.floor(options.maxAgeSeconds))}`,
    "HttpOnly",
    "SameSite=Lax",
  ];
  if (options.secure) parts.push("Secure");
  return parts.join("; ");
}

export function clearCookie(name: string, secure: boolean): string {
  return serializeCookie(name, "", { maxAgeSeconds: 0, secure });
}
