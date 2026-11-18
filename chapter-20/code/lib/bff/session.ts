import { tokenExpiresAt, isExpiringSoon } from "../auth/jwt";
import { backendRefresh, type TokenPair } from "./backend";
import { ACCESS_COOKIE, REFRESH_COOKIE, clearCookie, serializeCookie } from "./cookies";
import type { BffConfig } from "./config";

/** Turn a token pair into two Set-Cookie header values, with lifetimes taken from the tokens themselves. */
export function sessionCookies(pair: TokenPair, config: BffConfig): string[] {
  const nowSeconds = (config.now?.() ?? Date.now()) / 1000;
  const lifetime = (token: string, fallback: number) => {
    const exp = tokenExpiresAt(token);
    return exp === null ? fallback : exp - nowSeconds;
  };
  return [
    serializeCookie(ACCESS_COOKIE, pair.access, { maxAgeSeconds: lifetime(pair.access, 900), secure: config.secureCookies }),
    serializeCookie(REFRESH_COOKIE, pair.refresh, { maxAgeSeconds: lifetime(pair.refresh, 86_400), secure: config.secureCookies }),
  ];
}

export function clearSessionCookies(config: BffConfig): string[] {
  return [clearCookie(ACCESS_COOKIE, config.secureCookies), clearCookie(REFRESH_COOKIE, config.secureCookies)];
}

// Several browser requests can notice an expired token at the same moment. Refresh tokens ROTATE (each works once),
// so they must share ONE refresh call; a second call with the old token would look like token theft.
const inFlight = new Map<string, Promise<TokenPair>>();

export function refreshOnce(config: BffConfig, refreshToken: string, requestId: string): Promise<TokenPair> {
  let promise = inFlight.get(refreshToken);
  if (!promise) {
    promise = backendRefresh(config, refreshToken, requestId).finally(() => {
      setTimeout(() => inFlight.delete(refreshToken), 0);
    });
    inFlight.set(refreshToken, promise);
  }
  return promise;
}

export function accessNeedsRefresh(access: string | undefined, config: BffConfig): boolean {
  return isExpiringSoon(access, (config.now?.() ?? Date.now()) / 1000, config.accessSkewSeconds ?? 30);
}
