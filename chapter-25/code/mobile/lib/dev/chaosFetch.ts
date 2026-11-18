export interface ChaosOptions {
  base?: typeof fetch;
  /** Random delay range in ms added to every request. */
  latencyMs?: [min: number, max: number];
  /** 0 to 1. Half of the failures are dropped connections, half are 503 responses. */
  failureRate?: number;
  /** true, or a function, to behave as if the phone had no network. */
  offline?: boolean | (() => boolean);
  random?: () => number;
  delay?: (ms: number, signal?: AbortSignal | null) => Promise<void>;
}

const abortError = () => Object.assign(new Error('Aborted'), { name: 'AbortError' });

const abortableDelay = (ms: number, signal?: AbortSignal | null) =>
  new Promise<void>((resolve, reject) => {
    if (signal?.aborted) return reject(abortError());
    const onAbort = () => {
      clearTimeout(timer);
      reject(abortError());
    };
    const timer = setTimeout(() => {
      signal?.removeEventListener('abort', onAbort);
      resolve();
    }, ms);
    signal?.addEventListener('abort', onAbort, { once: true });
  });

/** A fetch that misbehaves on purpose. Wrap your real fetch with it in development only. */
export function createChaosFetch({
  base = fetch,
  latencyMs = [0, 0],
  failureRate = 0,
  offline = false,
  random = Math.random,
  delay = abortableDelay,
}: ChaosOptions = {}): typeof fetch {
  const isOffline = typeof offline === 'function' ? offline : () => offline;

  return async (input, init) => {
    const signal = init?.signal;
    const [min, max] = latencyMs;
    await delay(min + Math.floor(random() * (max - min)), signal);

    if (isOffline()) throw new TypeError('Network request failed');
    const roll = random();
    if (roll < failureRate / 2) throw new TypeError('Network request failed');
    if (roll < failureRate) return new Response('Service Unavailable', { status: 503, headers: { 'Retry-After': '1' } });
    return base(input, init);
  };
}
