import { ApiError, NetworkError, SessionExpiredError, TimeoutError, isRetryable } from "./errors";
import type { TokenStore } from "./tokenStore";

/** The small part of fetch we use. The real fetch fits, and so does a fake in tests. */
export interface ResponseLike {
  status: number;
  headers: { get(name: string): string | null };
  text(): Promise<string>;
}
export type FetchLike = (
  url: string,
  init: { method: string; headers: Record<string, string>; body?: string; signal?: AbortSignal },
) => Promise<ResponseLike>;

export interface LogEvent {
  method: string;
  path: string;
  status: number | "network-error" | "timeout";
  ms: number;
  requestId: string;
}

export interface ApiClientOptions {
  baseUrl: string;
  tokenStore: TokenStore;
  fetch?: FetchLike;
  /** Where to exchange a refresh token for a new access token. Match your backend (Chapter 13). */
  refreshPath?: string;
  timeoutMs?: number;
  maxRetries?: number;
  baseDelayMs?: number;
  maxDelayMs?: number;
  /** Refresh a little early, so the user's request does not waste a round trip on a 401. */
  refreshSkewMs?: number;
  sleep?: (ms: number) => Promise<void>;
  random?: () => number;
  now?: () => number;
  makeRequestId?: () => string;
  onSessionExpired?: () => void;
  /** Never receives bodies, headers or tokens: only what is needed to see how the app is doing. */
  onLog?: (event: LogEvent) => void;
}

export interface RequestOptions {
  body?: unknown;
  headers?: Record<string, string>;
  /** Makes it safe to retry a POST or PATCH: the server must treat the same key as the same request. */
  idempotencyKey?: string;
  signal?: AbortSignal;
  /** Set false for public endpoints such as sign in. */
  auth?: boolean;
}

const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);

function defaultRequestId(): string {
  return `req_${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`;
}

export class ApiClient {
  private readonly fetchImpl: FetchLike;
  private readonly opts: Required<
    Pick<ApiClientOptions, "refreshPath" | "timeoutMs" | "maxRetries" | "baseDelayMs" | "maxDelayMs" | "refreshSkewMs">
  >;
  private refreshing: Promise<void> | null = null;

  constructor(private readonly o: ApiClientOptions) {
    this.fetchImpl = o.fetch ?? (globalThis.fetch as unknown as FetchLike);
    this.opts = {
      refreshPath: o.refreshPath ?? "/api/v1/auth/refresh/",
      timeoutMs: o.timeoutMs ?? 15_000,
      maxRetries: o.maxRetries ?? 3,
      baseDelayMs: o.baseDelayMs ?? 500,
      maxDelayMs: o.maxDelayMs ?? 8_000,
      refreshSkewMs: o.refreshSkewMs ?? 30_000,
    };
  }

  get<T>(path: string, opts: RequestOptions = {}): Promise<T> {
    return this.request<T>("GET", path, opts);
  }
  post<T>(path: string, body?: unknown, opts: RequestOptions = {}): Promise<T> {
    return this.request<T>("POST", path, { ...opts, body });
  }
  patch<T>(path: string, body?: unknown, opts: RequestOptions = {}): Promise<T> {
    return this.request<T>("PATCH", path, { ...opts, body });
  }
  delete<T>(path: string, opts: RequestOptions = {}): Promise<T> {
    return this.request<T>("DELETE", path, opts);
  }

  /**
   * Retries happen only when repeating the request cannot do harm: reads, or writes that carry an
   * idempotency key. A POST without a key is never repeated automatically, because if the first
   * one actually reached the server, a retry could create a second order.
   */
  async request<T>(method: string, path: string, opts: RequestOptions = {}): Promise<T> {
    const upper = method.toUpperCase();
    const mayRetry = SAFE_METHODS.has(upper) || Boolean(opts.idempotencyKey);
    for (let attempt = 0; ; attempt++) {
      try {
        return await this.once<T>(upper, path, opts);
      } catch (error) {
        if (!mayRetry || !isRetryable(error) || attempt >= this.opts.maxRetries) throw error;
        await (this.o.sleep ?? defaultSleep)(this.delayFor(attempt, error));
      }
    }
  }

  private delayFor(attempt: number, error: unknown): number {
    if (error instanceof ApiError && error.retryAfterMs !== undefined) {
      return Math.min(error.retryAfterMs, this.opts.maxDelayMs * 4);
    }
    const ceiling = Math.min(this.opts.maxDelayMs, this.opts.baseDelayMs * 2 ** attempt);
    const random = (this.o.random ?? Math.random)();
    return Math.round(ceiling / 2 + (ceiling / 2) * random); // "equal jitter": never zero, never in lockstep
  }

  private async once<T>(method: string, path: string, opts: RequestOptions, afterRefresh = false): Promise<T> {
    const useAuth = opts.auth !== false;
    if (useAuth && !afterRefresh) await this.refreshIfExpiring();
    const tokens = useAuth ? await this.o.tokenStore.get() : null;
    const requestId = (this.o.makeRequestId ?? defaultRequestId)();
    const headers: Record<string, string> = {
      Accept: "application/json",
      "X-Request-ID": requestId,
      ...opts.headers,
    };
    if (opts.body !== undefined) headers["Content-Type"] = "application/json";
    if (tokens) headers.Authorization = `Bearer ${tokens.access}`;
    if (opts.idempotencyKey) headers["Idempotency-Key"] = opts.idempotencyKey;

    const started = (this.o.now ?? Date.now)();
    let response: ResponseLike;
    try {
      response = await this.send(`${this.o.baseUrl}${path}`, {
        method,
        headers,
        body: opts.body === undefined ? undefined : JSON.stringify(opts.body),
        signal: opts.signal,
      });
    } catch (error) {
      this.log({ method, path, status: error instanceof TimeoutError ? "timeout" : "network-error", requestId, started });
      throw error;
    }
    this.log({ method, path, status: response.status, requestId, started });

    if (response.status === 401 && useAuth && !afterRefresh) {
      await this.refresh();
      return this.once<T>(method, path, opts, true);
    }
    return this.parse<T>(response);
  }

  private log(e: { method: string; path: string; status: LogEvent["status"]; requestId: string; started: number }) {
    this.o.onLog?.({ method: e.method, path: e.path, status: e.status, requestId: e.requestId, ms: (this.o.now ?? Date.now)() - e.started });
  }

  private async send(url: string, init: Parameters<FetchLike>[1]): Promise<ResponseLike> {
    const controller = new AbortController();
    const outer = init.signal;
    if (outer) {
      if (outer.aborted) controller.abort();
      else outer.addEventListener("abort", () => controller.abort(), { once: true });
    }
    let timedOut = false;
    const timer = setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, this.opts.timeoutMs);
    try {
      return await this.fetchImpl(url, { ...init, signal: controller.signal });
    } catch (error) {
      if (timedOut) throw new TimeoutError();
      if (outer?.aborted) throw error; // the caller cancelled: not a network problem
      throw new NetworkError();
    } finally {
      clearTimeout(timer);
    }
  }

  private async parse<T>(response: ResponseLike): Promise<T> {
    const text = await response.text();
    let body: unknown = undefined;
    if (text) {
      try {
        body = JSON.parse(text);
      } catch {
        body = undefined; // an HTML error page, for example. Never show it to the user.
      }
    }
    if (response.status >= 200 && response.status < 300) {
      if (response.status === 204 || text === "") return undefined as T;
      if (body === undefined) throw new ApiError(response.status, "invalid_json", "The server sent an unreadable answer");
      return body as T;
    }
    const obj = (typeof body === "object" && body !== null ? body : {}) as Record<string, unknown>;
    const seconds = Number(response.headers.get("Retry-After"));
    throw new ApiError(
      response.status,
      typeof obj.code === "string" ? obj.code : `http_${response.status}`,
      typeof obj.detail === "string" ? obj.detail : typeof obj.message === "string" ? obj.message : `Request failed (${response.status})`,
      body,
      Number.isFinite(seconds) && seconds > 0 ? seconds * 1000 : undefined,
    );
  }

  private async refreshIfExpiring(): Promise<void> {
    const tokens = await this.o.tokenStore.get();
    if (tokens?.accessExpiresAt !== undefined && (this.o.now ?? Date.now)() + this.opts.refreshSkewMs >= tokens.accessExpiresAt) {
      await this.refresh();
    }
  }

  /**
   * Many requests can get a 401 at the same moment. They must share ONE refresh: refresh tokens are
   * often single-use, so a second refresh would use an already-spent token and sign the user out.
   */
  refresh(): Promise<void> {
    if (!this.refreshing) {
      this.refreshing = this.doRefresh().finally(() => {
        this.refreshing = null;
      });
    }
    return this.refreshing;
  }

  private async doRefresh(): Promise<void> {
    const tokens = await this.o.tokenStore.get();
    if (!tokens) throw new SessionExpiredError();
    let response: ResponseLike;
    try {
      response = await this.send(`${this.o.baseUrl}${this.opts.refreshPath}`, {
        method: "POST",
        headers: { Accept: "application/json", "Content-Type": "application/json" },
        body: JSON.stringify({ refresh: tokens.refresh }),
      });
    } catch (error) {
      throw error; // offline or slow: keep the tokens, the user is NOT signed out
    }
    if ([400, 401, 403].includes(response.status)) {
      await this.o.tokenStore.clear();
      this.o.onSessionExpired?.();
      throw new SessionExpiredError();
    }
    const data = (await this.parse<{ access: string; refresh?: string; expires_in?: number }>(response));
    await this.o.tokenStore.set({
      access: data.access,
      refresh: data.refresh ?? tokens.refresh, // keep the old one if the server does not rotate
      accessExpiresAt: data.expires_in ? (this.o.now ?? Date.now)() + data.expires_in * 1000 : undefined,
    });
  }
}

function defaultSleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
