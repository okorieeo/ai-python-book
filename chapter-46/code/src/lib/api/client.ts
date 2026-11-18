import createClient from "openapi-fetch";
import type { paths } from "./schema";
import { ApiError, networkError, toApiError } from "./errors";
import { getAccessToken, setAccessToken } from "../auth/session";

export const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type FetchLike = (request: Request) => Promise<Response>;

const AUTH_PATHS = ["/api/v1/auth/login/", "/api/v1/auth/refresh/"];

function isAuthPath(url: string): boolean {
  const { pathname } = new URL(url);
  return AUTH_PATHS.includes(pathname);
}

export function createApi(baseFetch: FetchLike = (request) => fetch(request), baseUrl = API_BASE_URL) {
  // One refresh at a time: ten requests that all get a 401 must trigger ONE refresh.
  let refreshing: Promise<string | null> | null = null;

  async function refreshAccessToken(): Promise<string | null> {
    refreshing ??= (async () => {
      try {
        const response = await baseFetch(
          new Request(`${baseUrl}/api/v1/auth/refresh/`, {
            method: "POST",
            credentials: "include",
          }),
        );
        if (!response.ok) return null;
        const body: unknown = await response.json();
        const access =
          typeof body === "object" && body !== null && "access" in body
            ? (body as { access: unknown }).access
            : null;
        return typeof access === "string" ? access : null;
      } catch {
        return null;
      } finally {
        refreshing = null;
      }
    })();
    return refreshing;
  }

  const authFetch: FetchLike = async (request) => {
    const retry = request.clone(); // clone before the body is consumed
    const token = getAccessToken();
    if (token && !isAuthPath(request.url)) {
      request.headers.set("Authorization", `Bearer ${token}`);
    }

    let response: Response;
    try {
      response = await baseFetch(request);
    } catch {
      throw networkError();
    }

    if (response.status !== 401 || isAuthPath(request.url)) return response;

    const fresh = await refreshAccessToken();
    setAccessToken(fresh);
    if (!fresh) return response; // the caller sees the 401 and sends the user to sign in

    retry.headers.set("Authorization", `Bearer ${fresh}`);
    try {
      return await baseFetch(retry);
    } catch {
      throw networkError();
    }
  };

  return createClient<paths>({ baseUrl, fetch: authFetch, credentials: "include" });
}

export const api = createApi();

// Turns openapi-fetch's { data, error, response } into "return the data or throw ApiError",
// so components never have to remember to check `error`.
export async function unwrap<T>(
  call: Promise<{ data?: T; error?: unknown; response: Response }>,
): Promise<T> {
  const { data, error, response } = await call;
  if (!response.ok) throw toApiError(response.status, error, response.headers);
  return data as T;
}

export { ApiError };
