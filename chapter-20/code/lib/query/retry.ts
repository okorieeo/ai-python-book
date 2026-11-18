import { isRetryable } from "../api/errors";

/** TanStack Query retry rule: retry transient failures a couple of times, never client errors. */
export function shouldRetry(failureCount: number, error: unknown, maxRetries = 2): boolean {
  return failureCount < maxRetries && isRetryable(error);
}

/** Exponential delay with a cap: 500 ms, 1 s, 2 s... */
export function retryDelay(attemptIndex: number): number {
  return Math.min(500 * 2 ** attemptIndex, 8000);
}
