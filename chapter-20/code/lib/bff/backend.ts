import { ApiError, errorFromResponse } from "../api/errors";
import type { User } from "../api/types";
import type { BffConfig } from "./config";

export type TokenPair = { access: string; refresh: string };
export type LoginResult = TokenPair & { user: User };

/** Server-to-server calls to Django for the three token operations. */
async function post(config: BffConfig, path: string, body: unknown, requestId: string): Promise<Response> {
  try {
    return await fetch(`${config.backendUrl}/api/v1${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json", "X-Request-ID": requestId },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(config.timeoutMs ?? 15_000),
    });
  } catch {
    throw new ApiError({ status: 502, code: "upstream_unavailable", message: "The backend could not be reached.", requestId });
  }
}

export async function backendLogin(config: BffConfig, email: string, password: string, requestId: string): Promise<LoginResult> {
  const response = await post(config, "/auth/login", { email, password }, requestId);
  if (!response.ok) throw await errorFromResponse(response);
  return (await response.json()) as LoginResult;
}

export async function backendRefresh(config: BffConfig, refresh: string, requestId: string): Promise<TokenPair> {
  const response = await post(config, "/auth/refresh", { refresh }, requestId);
  if (!response.ok) throw await errorFromResponse(response);
  return (await response.json()) as TokenPair;
}

export async function backendLogout(config: BffConfig, refresh: string, requestId: string): Promise<void> {
  try {
    await post(config, "/auth/logout", { refresh }, requestId);
  } catch {
    // Logging out must always succeed locally, even if the backend is unreachable
  }
}
