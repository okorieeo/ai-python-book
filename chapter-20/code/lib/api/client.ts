import { ApiError, errorFromResponse } from "./errors";
import { buildQuery, type QueryValue } from "./query-string";

export type RequestOptions = {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  query?: Record<string, QueryValue>;
  body?: unknown;
  headers?: Record<string, string>;
  idempotencyKey?: string;
  signal?: AbortSignal;
  timeoutMs?: number;
};

export type ApiClientConfig = {
  baseUrl?: string; // "/api/v1" in the browser: same origin, so no CORS and cookies are sent automatically
  fetchFn?: typeof fetch;
  defaultTimeoutMs?: number;
  onSessionExpired?: () => void;
};

export type ApiClient = ReturnType<typeof createApiClient>;

export function createApiClient(config: ApiClientConfig = {}) {
  const baseUrl = config.baseUrl ?? "/api/v1";
  const fetchFn = config.fetchFn ?? ((input, init) => fetch(input, init));
  const defaultTimeoutMs = config.defaultTimeoutMs ?? 20_000;

  async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
    const method = options.method ?? "GET";
    const headers: Record<string, string> = { Accept: "application/json", ...options.headers };
    if (options.body !== undefined) headers["Content-Type"] = "application/json";
    if (options.idempotencyKey) headers["Idempotency-Key"] = options.idempotencyKey;

    // One controller combines the caller's cancellation (TanStack Query) with our timeout
    const controller = new AbortController();
    const timeoutMs = options.timeoutMs ?? defaultTimeoutMs;
    let timedOut = false;
    const timer = setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, timeoutMs);
    const onCallerAbort = () => controller.abort();
    if (options.signal) {
      if (options.signal.aborted) controller.abort();
      else options.signal.addEventListener("abort", onCallerAbort, { once: true });
    }

    try {
      const response = await fetchFn(`${baseUrl}${path}${buildQuery(options.query)}`, {
        method,
        headers,
        body: options.body === undefined ? undefined : JSON.stringify(options.body),
        credentials: "same-origin",
        signal: controller.signal,
      });
      if (!response.ok) {
        const error = await errorFromResponse(response);
        if (error.code === "session_expired") config.onSessionExpired?.();
        throw error;
      }
      if (response.status === 204) return undefined as T;
      return (await response.json()) as T;
    } catch (error) {
      if (error instanceof ApiError) throw error;
      if (timedOut) throw new ApiError({ status: 0, code: "timeout", message: `Request timed out after ${timeoutMs} ms` });
      if (options.signal?.aborted) throw error; // the caller cancelled: let the abort error through untouched
      throw new ApiError({ status: 0, code: "network_error", message: "Network error" });
    } finally {
      clearTimeout(timer);
      options.signal?.removeEventListener("abort", onCallerAbort);
    }
  }

  return {
    request,
    get: <T>(path: string, options: Omit<RequestOptions, "method" | "body"> = {}) => request<T>(path, { ...options, method: "GET" }),
    post: <T>(path: string, body?: unknown, options: Omit<RequestOptions, "method" | "body"> = {}) => request<T>(path, { ...options, method: "POST", body }),
    patch: <T>(path: string, body?: unknown, options: Omit<RequestOptions, "method" | "body"> = {}) => request<T>(path, { ...options, method: "PATCH", body }),
    delete: <T>(path: string, options: Omit<RequestOptions, "method" | "body"> = {}) => request<T>(path, { ...options, method: "DELETE" }),
  };
}
