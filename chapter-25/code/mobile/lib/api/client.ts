import { isUnauthorized } from '../net/errors';
import { requestJson, type JsonOptions } from '../net/fetchWithTimeout';
import { withRetry, type RetryOptions } from '../net/retry';

export interface ApiConfig {
  /** For example https://api.example.com/api/v1 (no trailing slash). */
  baseUrl: string;
  /** Your Chapter 24 token store. Called on every attempt so a refreshed token is used. */
  getToken: () => Promise<string | null>;
  /** Called after a 401, so Chapter 24's refresh or sign-out logic can run. */
  onUnauthorized?: () => void;
  fetchImpl?: typeof fetch;
}

let config: ApiConfig | null = null;

export function configureApi(next: ApiConfig): void {
  config = next;
}

export interface ApiRequestOptions<T> extends Omit<JsonOptions<T>, 'body' | 'method' | 'headers'> {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  body?: unknown;
  headers?: Record<string, string>;
  /** true only when repeating is safe: all GETs, and writes that carry an idempotency key. */
  idempotent?: boolean;
  /**
   * Retries inside this call. Default 0, on purpose: React Query (reads) and the outbox (writes)
   * already retry. Retrying in two layers multiplies the attempts.
   */
  retries?: number;
  retry?: Pick<RetryOptions, 'baseDelayMs' | 'maxDelayMs' | 'deadlineMs'>;
}

export async function apiRequest<T = unknown>(path: string, options: ApiRequestOptions<T> = {}): Promise<T> {
  if (!config) throw new Error('Call configureApi() before the first request.');
  const { baseUrl, getToken, onUnauthorized, fetchImpl } = config;
  const { method = 'GET', body, headers, idempotent = method === 'GET', retries = 0, retry, ...rest } = options;

  return withRetry(
    async () => {
      const token = await getToken();
      try {
        return await requestJson<T>(`${baseUrl}${path}`, {
          ...rest,
          method,
          fetchImpl: rest.fetchImpl ?? fetchImpl,
          headers: {
            Accept: 'application/json',
            ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
            ...headers,
          },
          body: body === undefined ? undefined : JSON.stringify(body),
        });
      } catch (error) {
        if (isUnauthorized(error)) onUnauthorized?.();
        throw error;
      }
    },
    { ...retry, idempotent, retries, signal: rest.signal },
  );
}
