import { ApiError } from "../api/errors";
import type { User } from "../api/types";
import { backendLogin, backendLogout } from "./backend";
import type { BffConfig } from "./config";
import { REFRESH_COOKIE, parseCookies } from "./cookies";
import { errorResponse, isCrossSiteRequest, requestIdFor } from "./gateway";
import { clearSessionCookies, sessionCookies } from "./session";

function jsonResponse(data: unknown, status: number, requestId: string, cookies: string[] = []): Response {
  const headers = new Headers({ "Content-Type": "application/json", "Cache-Control": "no-store", "X-Request-ID": requestId });
  for (const cookie of cookies) headers.append("Set-Cookie", cookie);
  return new Response(data === null ? null : JSON.stringify(data), { status, headers });
}

/** POST /api/auth/login: exchange email and password for HttpOnly cookies. The browser only ever receives the user. */
export async function handleLogin(request: Request, config: BffConfig): Promise<Response> {
  const requestId = requestIdFor(request);
  if (isCrossSiteRequest(request, config.appOrigin)) return errorResponse(403, "csrf_blocked", "Cross-site requests are not allowed.", requestId);

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return errorResponse(400, "invalid_json", "The request body is not valid JSON.", requestId);
  }
  const { email, password } = (typeof body === "object" && body !== null ? body : {}) as { email?: unknown; password?: unknown };
  if (typeof email !== "string" || typeof password !== "string" || !email || !password) {
    return jsonResponse({ error: { code: "validation_error", message: "The request data is invalid.", details: {
      ...(typeof email === "string" && email ? {} : { email: ["This field is required."] }),
      ...(typeof password === "string" && password ? {} : { password: ["This field is required."] }),
    } }, request_id: requestId }, 400, requestId);
  }

  try {
    const { access, refresh, user } = await backendLogin(config, email, password, requestId);
    return jsonResponse({ user }, 200, requestId, sessionCookies({ access, refresh }, config));
  } catch (error) {
    if (error instanceof ApiError) {
      return jsonResponse({ error: { code: error.code, message: error.message, details: error.details }, request_id: requestId }, error.status || 502, requestId);
    }
    return errorResponse(502, "upstream_unavailable", "The service is temporarily unavailable.", requestId);
  }
}

/** POST /api/auth/logout: revoke the session on the backend (best effort) and always clear the cookies. */
export async function handleLogout(request: Request, config: BffConfig): Promise<Response> {
  const requestId = requestIdFor(request);
  if (isCrossSiteRequest(request, config.appOrigin)) return errorResponse(403, "csrf_blocked", "Cross-site requests are not allowed.", requestId);
  const refresh = parseCookies(request.headers.get("cookie"))[REFRESH_COOKIE];
  if (refresh) await backendLogout(config, refresh, requestId);
  return jsonResponse(null, 204, requestId, clearSessionCookies(config));
}

export type { User };
