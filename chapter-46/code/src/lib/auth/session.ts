// The access token lives in memory only. A page reload loses it, and the
// refresh cookie (HttpOnly, set by Django) gets a new one. See 46.5.
let accessToken: string | null = null;

export function getAccessToken(): string | null {
  return accessToken;
}

export function setAccessToken(token: string | null): void {
  accessToken = token;
}

export function clearSession(): void {
  accessToken = null;
}
