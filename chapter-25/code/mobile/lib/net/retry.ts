import { ApiError, isRetryable } from './errors';

export interface BackoffOptions {
  baseDelayMs?: number;
  maxDelayMs?: number;
  random?: () => number;
}

/**
 * Exponential backoff with "full jitter": wait a random time between 0 and min(max, base * 2^attempt).
 * `attempt` counts retries from 0. The randomness stops thousands of phones from retrying in lockstep.
 */
export function backoffDelay(
  attempt: number,
  { baseDelayMs = 500, maxDelayMs = 30_000, random = Math.random }: BackoffOptions = {},
): number {
  const ceiling = Math.min(maxDelayMs, baseDelayMs * 2 ** Math.max(0, attempt));
  return Math.floor(random() * ceiling);
}

export type Sleep = (ms: number, signal?: AbortSignal | null) => Promise<void>;

export const sleep: Sleep = (ms, signal) =>
  new Promise<void>((resolve, reject) => {
    if (signal?.aborted) return reject(new ApiError({ kind: 'aborted' }));
    const onAbort = () => {
      clearTimeout(timer);
      reject(new ApiError({ kind: 'aborted' }));
    };
    const timer = setTimeout(() => {
      signal?.removeEventListener('abort', onAbort);
      resolve();
    }, ms);
    signal?.addEventListener('abort', onAbort, { once: true });
  });

export interface RetryOptions extends BackoffOptions {
  /** Is it safe to send this request twice? GET: yes. POST: only with an idempotency key. */
  idempotent: boolean;
  /** Retries after the first attempt. Default 3 (so at most 4 tries). */
  retries?: number;
  signal?: AbortSignal | null;
  /** Total time budget in ms, including waiting. Stops early instead of waiting past it. */
  deadlineMs?: number;
  now?: () => number;
  sleep?: Sleep;
  onRetry?: (info: { attempt: number; delayMs: number; error: ApiError }) => void;
}

export async function withRetry<T>(run: (attempt: number) => Promise<T>, options: RetryOptions): Promise<T> {
  const { idempotent, retries = 3, signal, deadlineMs, now = Date.now, sleep: wait = sleep, onRetry } = options;
  const maxDelayMs = options.maxDelayMs ?? 30_000;
  const startedAt = now();

  for (let attempt = 0; ; attempt++) {
    try {
      return await run(attempt);
    } catch (error) {
      if (attempt >= retries || !isRetryable(error, { idempotent })) throw error;
      const apiError = error as ApiError;

      let delayMs = backoffDelay(attempt, options);
      if (apiError.retryAfterMs !== undefined) {
        // The server told us when to come back. Never earlier, and if it is "much later",
        // do not hold this request open: let the caller decide (the outbox reschedules).
        if (apiError.retryAfterMs > maxDelayMs) throw error;
        delayMs = Math.max(delayMs, apiError.retryAfterMs);
      }
      if (deadlineMs !== undefined && now() - startedAt + delayMs > deadlineMs) throw error;

      onRetry?.({ attempt, delayMs, error: apiError });
      await wait(delayMs, signal);
    }
  }
}
