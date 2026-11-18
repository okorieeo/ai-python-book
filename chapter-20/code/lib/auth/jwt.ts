/** Read the contents of a JWT WITHOUT verifying it. Only the server can verify; we only need to know when it expires. */
export function decodeJwtPayload(token: string): Record<string, unknown> | null {
  const parts = token.split(".");
  if (parts.length !== 3) return null;
  try {
    const base64 = parts[1].replace(/-/g, "+").replace(/_/g, "/");
    const binary = atob(base64 + "=".repeat((4 - (base64.length % 4)) % 4));
    const bytes = Uint8Array.from(binary, (char) => char.charCodeAt(0));
    const payload: unknown = JSON.parse(new TextDecoder().decode(bytes));
    return typeof payload === "object" && payload !== null && !Array.isArray(payload) ? (payload as Record<string, unknown>) : null;
  } catch {
    return null;
  }
}

/** Expiry as seconds since the epoch, or null if the token is unreadable or has no `exp`. */
export function tokenExpiresAt(token: string): number | null {
  const exp = decodeJwtPayload(token)?.exp;
  return typeof exp === "number" ? exp : null;
}

/** True if the token is missing, unreadable, expired, or will expire within `skewSeconds`. */
export function isExpiringSoon(token: string | undefined, nowSeconds: number, skewSeconds = 30): boolean {
  if (!token) return true;
  const exp = tokenExpiresAt(token);
  return exp === null || exp - skewSeconds <= nowSeconds;
}
