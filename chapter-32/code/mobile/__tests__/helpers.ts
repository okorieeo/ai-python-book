import { ApiError } from '../lib/net/errors';

export const networkError = () => new ApiError({ kind: 'network' });
export const timeoutError = () => new ApiError({ kind: 'timeout' });
export const httpError = (status: number, retryAfterMs?: number) => new ApiError({ kind: 'http', status, retryAfterMs });

export const json = (data: unknown, init: ResponseInit = {}) =>
  new Response(JSON.stringify(data), { status: 200, headers: { 'Content-Type': 'application/json' }, ...init });

export const abortError = () => Object.assign(new Error('Aborted'), { name: 'AbortError' });

/** A promise you resolve by hand: lets a test freeze a request in flight. */
export function deferred<T = void>() {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

/** A fetch that never answers until it is aborted, like a dead connection. */
export const hangingFetch: typeof fetch = (_url, init) =>
  new Promise((_resolve, reject) => {
    init?.signal?.addEventListener('abort', () => reject(abortError()), { once: true });
  });
