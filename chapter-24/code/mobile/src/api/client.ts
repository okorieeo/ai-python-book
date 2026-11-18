import type { TokenStore } from "../auth/tokenStore";
import { ApiError, NetworkError } from "./errors";

export interface ClientOptions {
  baseUrl: string; // e.g. http://192.168.1.20:8000/api/v1
  store: TokenStore;
  onSignedOut: () => void; // called when the server says our session is over
  fetchFn?: typeof fetch; // replaced by a fake in tests
  timeoutMs?: number;
}

export interface RequestOptions {
  body?: unknown; // sent as JSON
  form?: FormData; // sent as multipart (uploads); use instead of body
  auth?: boolean; // default true: send the access token
  query?: Record<string, string | number | undefined>;
}

// 400 and 401 from the refresh endpoint mean "this refresh token is finished".
// A 429 or 5xx means "try again later": that must NOT sign anyone out.
const isSessionOver = (e: unknown) =>
  e instanceof ApiError && (e.status === 401 || e.status === 400);

export function createApiClient(options: ClientOptions) {
  const { baseUrl, store, onSignedOut } = options;
  const doFetch = options.fetchFn ?? fetch;
  const timeoutMs = options.timeoutMs ?? 15_000;
  let refreshing: Promise<void> | null = null; // the one refresh in flight

  function buildUrl(path: string, query?: RequestOptions["query"]) {
    const pairs = Object.entries(query ?? {}).filter(([, v]) => v !== undefined);
    const qs = pairs
      .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`)
      .join("&");
    return baseUrl + path + (qs ? `?${qs}` : "");
  }

  async function send(
    method: string,
    path: string,
    o: RequestOptions,
    token: string | null,
  ): Promise<Response> {
    const headers: Record<string, string> = { Accept: "application/json" };
    let body: BodyInit | undefined;
    if (o.form) {
      body = o.form; // never set Content-Type here: fetch adds the multipart boundary
    } else if (o.body !== undefined) {
      headers["Content-Type"] = "application/json";
      body = JSON.stringify(o.body);
    }
    if (token) headers.Authorization = `Bearer ${token}`;

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      return await doFetch(buildUrl(path, o.query), {
        method,
        headers,
        body,
        signal: controller.signal,
      });
    } catch {
      if (controller.signal.aborted) throw new NetworkError("The request timed out.", true);
      throw new NetworkError();
    } finally {
      clearTimeout(timer);
    }
  }

  async function parse<T>(res: Response): Promise<T> {
    if (res.status === 204) return undefined as T;
    const text = await res.text();
    let json: any = null;
    try {
      json = text ? JSON.parse(text) : null;
    } catch {
      json = null; // a proxy's HTML error page, for example
    }
    if (res.ok) return json as T;
    const err = json?.error; // the error format designed in Chapter 8
    throw new ApiError(
      res.status,
      err?.code ?? "http_error",
      err?.message ?? `Request failed (${res.status}).`,
      err?.details,
      err?.request_id,
    );
  }

  async function doRefresh(): Promise<void> {
    const refresh = await store.getRefresh();
    if (!refresh) throw new ApiError(401, "not_authenticated", "Not signed in.");
    const res = await send("POST", "/auth/token/refresh", { body: { refresh } }, null);
    // With rotation on (Chapter 13) the answer holds a NEW refresh token.
    // We must save it, or the next refresh uses a token the server already burned.
    await store.setTokens(await parse<{ access: string; refresh?: string }>(res));
  }

  // Ten requests that all get a 401 at once must cause ONE refresh, not ten.
  // Rotation would make nine of them fail: the first one burns the token.
  function refreshSession(): Promise<void> {
    if (!refreshing) {
      refreshing = doRefresh().finally(() => {
        refreshing = null;
      });
    }
    return refreshing;
  }

  async function endSession() {
    await store.clear();
    onSignedOut();
  }

  async function request<T>(method: string, path: string, o: RequestOptions = {}): Promise<T> {
    const useAuth = o.auth !== false;
    let res = await send(method, path, o, useAuth ? store.getAccess() : null);

    if (res.status === 401 && useAuth) {
      try {
        await refreshSession();
      } catch (e) {
        if (isSessionOver(e)) await endSession(); // really signed out
        throw e; // a NetworkError or a 5xx: stay signed in, report the problem
      }
      res = await send(method, path, o, store.getAccess()); // one retry, no more
      if (res.status === 401) await endSession();
    }
    return parse<T>(res);
  }

  /** Called once at launch: turn the stored refresh token into a working session. */
  async function restoreSession(): Promise<boolean> {
    if (!(await store.getRefresh())) return false;
    try {
      await refreshSession();
      return true;
    } catch (e) {
      if (isSessionOver(e)) {
        await store.clear();
        return false;
      }
      throw e; // offline at launch: the caller decides what to show
    }
  }

  return {
    request,
    restoreSession,
    get: <T>(path: string, o?: RequestOptions) => request<T>("GET", path, o),
    post: <T>(path: string, body?: unknown, o?: RequestOptions) =>
      request<T>("POST", path, { ...o, body }),
    patch: <T>(path: string, body?: unknown, o?: RequestOptions) =>
      request<T>("PATCH", path, { ...o, body }),
    put: <T>(path: string, o?: RequestOptions) => request<T>("PUT", path, o),
    del: <T = void>(path: string, o?: RequestOptions) => request<T>("DELETE", path, o),
  };
}

export type ApiClient = ReturnType<typeof createApiClient>;
