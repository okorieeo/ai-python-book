import { ApiError } from './errors';

export const DEFAULT_TIMEOUT_MS = 15_000;

export interface FetchOptions extends Omit<RequestInit, 'signal'> {
  /** Cancels the request from outside, for example when a screen closes. */
  signal?: AbortSignal | null;
  /** The whole attempt must finish within this time (default 15 s). */
  timeoutMs?: number;
  /** Swap in a fake (tests) or a "chaos" fetch (development). */
  fetchImpl?: typeof fetch;
}

/**
 * Runs `run` with an AbortSignal that fires when the time is up or when the caller cancels.
 * We use a plain timer instead of AbortSignal.timeout() so it behaves the same in every
 * React Native version, and so we always know which of the two caused the abort.
 */
async function runWithDeadline<T>(
  timeoutMs: number,
  outer: AbortSignal | null | undefined,
  run: (signal: AbortSignal) => Promise<T>,
): Promise<T> {
  if (outer?.aborted) throw new ApiError({ kind: 'aborted' });
  const controller = new AbortController();
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);
  const onOuterAbort = () => controller.abort();
  outer?.addEventListener('abort', onOuterAbort, { once: true });

  try {
    return await run(controller.signal);
  } catch (error) {
    if (error instanceof ApiError) throw error; // already classified (http, parse)
    if (timedOut) throw new ApiError({ kind: 'timeout', cause: error });
    if (controller.signal.aborted) throw new ApiError({ kind: 'aborted', cause: error });
    throw new ApiError({ kind: 'network', cause: error });
  } finally {
    clearTimeout(timer);
    outer?.removeEventListener('abort', onOuterAbort);
  }
}

/** Like fetch, but never waits forever and always rejects with an ApiError. Time ends when headers arrive. */
export function fetchWithTimeout(url: string, options: FetchOptions = {}): Promise<Response> {
  const { timeoutMs = DEFAULT_TIMEOUT_MS, signal, fetchImpl = fetch, ...init } = options;
  return runWithDeadline(timeoutMs, signal, (s) => fetchImpl(url, { ...init, signal: s }));
}

/** "30" (seconds) or an HTTP date. Returns milliseconds, or undefined when missing or invalid. */
export function parseRetryAfter(value: string | null, now: number = Date.now()): number | undefined {
  if (!value) return undefined;
  const trimmed = value.trim();
  if (/^\d+$/.test(trimmed)) return Number(trimmed) * 1000;
  const date = Date.parse(trimmed);
  return Number.isNaN(date) ? undefined : Math.max(0, date - now);
}

export interface JsonOptions<T> extends FetchOptions {
  /** Validate or convert the decoded JSON. Throw to reject it. */
  parse?: (data: unknown) => T;
}

/**
 * Fetch JSON with ONE deadline that covers the headers AND the body. A server that sends
 * headers and then stalls would otherwise hang the app after fetch() has already "succeeded".
 */
export function requestJson<T = unknown>(url: string, options: JsonOptions<T> = {}): Promise<T> {
  const { timeoutMs = DEFAULT_TIMEOUT_MS, signal, fetchImpl = fetch, parse, ...init } = options;
  return runWithDeadline(timeoutMs, signal, async (s) => {
    const response = await fetchImpl(url, { ...init, signal: s });
    const text = await response.text();

    if (!response.ok) {
      let body: unknown;
      try {
        body = JSON.parse(text);
      } catch {
        body = undefined; // an HTML error page from a proxy: do not keep it
      }
      throw new ApiError({
        kind: 'http',
        status: response.status,
        body,
        retryAfterMs: parseRetryAfter(response.headers.get('retry-after')),
      });
    }
    if (response.status === 204 || text === '') return undefined as T;

    let data: unknown;
    try {
      data = JSON.parse(text);
    } catch (cause) {
      // Typical cause: a captive-portal or proxy page answered with 200 and HTML.
      throw new ApiError({ kind: 'parse', cause });
    }
    try {
      return parse ? parse(data) : (data as T);
    } catch (cause) {
      throw new ApiError({ kind: 'parse', message: 'The response did not have the expected shape', cause });
    }
  });
}
