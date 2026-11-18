import { ApiError } from "../api/errors";
import { ACCESS_COOKIE, REFRESH_COOKIE, parseCookies } from "./cookies";
import type { BffConfig } from "./config";
import type { TokenPair } from "./backend";
import { accessNeedsRefresh, clearSessionCookies, refreshOnce, sessionCookies } from "./session";

const ALLOWED_METHODS = new Set(["GET", "POST", "PUT", "PATCH", "DELETE"]);
const UNSAFE_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);
// Only these request headers are forwarded. Cookies, Authorization and Host are deliberately NOT among them.
const FORWARD_REQUEST_HEADERS = ["content-type", "accept", "idempotency-key", "accept-language", "x-app-version"];
// Only these response headers come back to the browser.
const FORWARD_RESPONSE_HEADERS = ["content-type", "cache-control", "x-request-id", "retry-after", "location", "idempotent-replayed", "etag", "www-authenticate"];

export function errorResponse(status: number, code: string, message: string, requestId: string, extraCookies: string[] = []): Response {
  const headers = new Headers({ "Content-Type": "application/json", "Cache-Control": "no-store", "X-Request-ID": requestId });
  for (const cookie of extraCookies) headers.append("Set-Cookie", cookie);
  return new Response(JSON.stringify({ error: { code, message }, request_id: requestId }), { status, headers });
}

/** Block cross-site requests that carry our cookies. Browsers set Sec-Fetch-Site and Origin; scripts on other sites cannot forge them. */
export function isCrossSiteRequest(request: Request, appOrigin?: string): boolean {
  const site = request.headers.get("sec-fetch-site");
  if (site) return !["same-origin", "none"].includes(site);
  const origin = request.headers.get("origin");
  if (origin) return origin !== (appOrigin ?? new URL(request.url).origin);
  return false; // non-browser clients (curl, tests) send neither header
}

// Under /auth/ only these pass through the gateway, WITHOUT credentials. Login, refresh, logout and social login
// are handled by dedicated handlers that keep tokens out of the browser, so they are NOT reachable here.
const PUBLIC_PATHS = new Set(["auth/register", "auth/email/verify", "auth/password/reset", "auth/password/reset/confirm"]);

export function classifyPath(segments: string[]): "public" | "private" | "blocked" {
  const joined = segments.join("/");
  if (PUBLIC_PATHS.has(joined)) return "public";
  if (segments[0] === "auth") return "blocked";
  return "private";
}

function validSegments(segments: string[]): boolean {
  return segments.length > 0 && segments.every((s) => s !== "" && s !== "." && s !== ".." && !/[\/\\\u0000-\u001f]/.test(s));
}

export function requestIdFor(request: Request): string {
  const incoming = request.headers.get("x-request-id") ?? "";
  return /^[A-Za-z0-9._-]{8,64}$/.test(incoming) ? incoming : "req_" + globalThis.crypto.randomUUID().replace(/-/g, "").slice(0, 12);
}

async function callBackend(config: BffConfig, request: Request, segments: string[], body: ArrayBuffer | undefined, access: string | undefined, requestId: string): Promise<Response> {
  const incoming = new URL(request.url);
  const target = `${config.backendUrl}/api/v1/${segments.map(encodeURIComponent).join("/")}${incoming.search}`;
  const headers = new Headers();
  for (const name of FORWARD_REQUEST_HEADERS) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  if (access) headers.set("Authorization", `Bearer ${access}`);
  headers.set("X-Request-ID", requestId);
  return fetch(target, {
    method: request.method,
    headers,
    body: body && body.byteLength > 0 ? body : undefined,
    signal: AbortSignal.timeout(config.timeoutMs ?? 30_000),
    redirect: "manual",
  });
}

function passThrough(upstream: Response, cookies: string[], requestId: string): Response {
  const headers = new Headers();
  for (const name of FORWARD_RESPONSE_HEADERS) {
    const value = upstream.headers.get(name);
    if (value) headers.set(name, value);
  }
  for (const cookie of cookies) headers.append("Set-Cookie", cookie);
  if (!headers.has("x-request-id")) headers.set("x-request-id", requestId);
  return new Response([204, 304].includes(upstream.status) ? null : upstream.body, { status: upstream.status, headers });
}

/**
 * The gateway: every browser call to /api/v1/* passes through here.
 * It attaches the bearer token from the HttpOnly cookie, refreshes it when needed, and returns Django's answer.
 */
export async function forwardToBackend(request: Request, segments: string[], config: BffConfig): Promise<Response> {
  const requestId = requestIdFor(request);
  if (!ALLOWED_METHODS.has(request.method)) return errorResponse(405, "method_not_allowed", "Method not allowed.", requestId);
  if (!validSegments(segments)) return errorResponse(400, "validation_error", "Invalid path.", requestId);
  if (UNSAFE_METHODS.has(request.method) && isCrossSiteRequest(request, config.appOrigin)) {
    return errorResponse(403, "csrf_blocked", "Cross-site requests are not allowed.", requestId);
  }

  const kind = classifyPath(segments);
  if (kind === "blocked") return errorResponse(404, "not_found", "Unknown path.", requestId);
  if (kind === "public") {
    try {
      const body = UNSAFE_METHODS.has(request.method) ? await request.arrayBuffer() : undefined;
      const upstream = await callBackend(config, request, segments, body, undefined, requestId);
      return passThrough(upstream, [], requestId);
    } catch {
      return errorResponse(502, "upstream_unavailable", "The service is temporarily unavailable.", requestId);
    }
  }

  const cookies = parseCookies(request.headers.get("cookie"));
  let access: string | undefined = cookies[ACCESS_COOKIE];
  const refresh: string | undefined = cookies[REFRESH_COOKIE];
  if (!access && !refresh) return errorResponse(401, "not_authenticated", "Please log in to continue.", requestId);

  let newCookies: string[] = [];
  const doRefresh = async (): Promise<boolean> => {
    if (!refresh) return false;
    try {
      const pair: TokenPair = await refreshOnce(config, refresh, requestId);
      access = pair.access;
      newCookies = sessionCookies(pair, config);
      return true;
    } catch (error) {
      if (error instanceof ApiError && error.status === 502) throw error; // backend down: keep the session
      return false;
    }
  };
  const expired = () => errorResponse(401, "session_expired", "Your session has expired. Please log in again.", requestId, clearSessionCookies(config));

  try {
    if (accessNeedsRefresh(access, config) && !(await doRefresh())) return expired();

    const body = UNSAFE_METHODS.has(request.method) ? await request.arrayBuffer() : undefined;
    let upstream = await callBackend(config, request, segments, body, access!, requestId);

    if (upstream.status === 401 && newCookies.length === 0) {
      // The backend rejected a token we thought was fine (revoked, key rotated): refresh once and retry once
      await upstream.body?.cancel();
      if (!(await doRefresh())) return expired();
      upstream = await callBackend(config, request, segments, body, access!, requestId);
    }

    return passThrough(upstream, newCookies, requestId);
  } catch (error) {
    if (error instanceof ApiError && error.code === "upstream_unavailable") {
      return errorResponse(502, "upstream_unavailable", "The service is temporarily unavailable.", requestId);
    }
    const timedOut = error instanceof DOMException && error.name === "TimeoutError";
    return errorResponse(timedOut ? 504 : 502, "upstream_unavailable", "The service is temporarily unavailable.", requestId);
  }
}
