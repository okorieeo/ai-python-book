import { ApiError, isRetryable } from '../net/errors';
import { backoffDelay } from '../net/retry';

export const ONE_DAY_MS = 24 * 60 * 60 * 1000;
/** How long a saved cache may be shown. React Query needs gcTime to be at least this long. */
export const CACHE_MAX_AGE_MS = 7 * ONE_DAY_MS;

/** Bump when the SHAPE of cached data changes. Old caches are then thrown away on startup. */
export const CACHE_SCHEMA_VERSION = 1;

export const cacheBuster = (appVersion: string, schemaVersion: number = CACHE_SCHEMA_VERSION): string =>
  `${appVersion}:${schemaVersion}`;

/**
 * An allow-list of what may be written to the phone's storage. A new query is NOT saved until
 * you add its first key here, which is the safe default for private data.
 */
export const PERSISTED_QUERY_ROOTS: readonly string[] = ['conversations', 'messages'];

export function shouldPersistQuery(queryKey: readonly unknown[], status: string): boolean {
  const root = queryKey[0];
  return status === 'success' && typeof root === 'string' && PERSISTED_QUERY_ROOTS.includes(root);
}

/** TanStack Query's retry hook: at most 2 retries, and only for failures that can pass. */
export const queryRetry = (failureCount: number, error: unknown): boolean =>
  failureCount < 2 && isRetryable(error, { idempotent: true });

export const queryRetryDelay = (failureCount: number, error: unknown): number => {
  const serverWish = error instanceof ApiError ? (error.retryAfterMs ?? 0) : 0;
  return Math.max(backoffDelay(failureCount), serverWish);
};
