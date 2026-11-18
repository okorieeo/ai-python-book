// A WebSocket that survives phones.
// Phones lose signal in lifts, switch from Wi-Fi to 4G, and put apps to sleep.
// Each of those silently kills the connection, so the client must notice and reconnect,
// without hammering the server: wait longer after each failure, with random jitter so
// ten thousand phones do not all return at the same second.

export type SocketStatus = "idle" | "connecting" | "open" | "waiting" | "stopped";

export interface SocketLike {
  onopen: ((event: unknown) => void) | null;
  onmessage: ((event: { data: unknown }) => void) | null;
  onclose: ((event: { code: number }) => void) | null;
  onerror: ((event: unknown) => void) | null;
  close(code?: number): void;
}

export interface TimerApi {
  set(fn: () => void, ms: number): unknown;
  clear(handle: unknown): void;
}

export interface SocketOptions {
  getUrl: () => Promise<string>; // asked again before EVERY attempt: tickets are one-use
  onMessage: (message: unknown) => void;
  onStatus?: (status: SocketStatus) => void;
  factory?: (url: string) => SocketLike;
  timers?: TimerApi;
  random?: () => number;
  baseDelayMs?: number;
  maxDelayMs?: number;
}

// 4403 = "forbidden" from our server. Retrying cannot change the answer.
export const FATAL_CLOSE_CODES = new Set([4403]);

/** "Equal jitter": somewhere between half and all of an exponentially growing delay. */
export function backoffDelay(
  attempt: number,
  baseMs: number,
  maxMs: number,
  random: () => number,
): number {
  const ceiling = Math.min(maxMs, baseMs * 2 ** attempt);
  return Math.round(ceiling / 2 + (random() * ceiling) / 2);
}

export function createSocket(options: SocketOptions) {
  const factory = options.factory ?? ((url: string) => new WebSocket(url) as unknown as SocketLike);
  const timers: TimerApi = options.timers ?? {
    set: (fn, ms) => setTimeout(fn, ms),
    clear: (handle) => clearTimeout(handle as ReturnType<typeof setTimeout>),
  };
  const random = options.random ?? Math.random;
  const baseMs = options.baseDelayMs ?? 1000;
  const maxMs = options.maxDelayMs ?? 30_000;

  let status: SocketStatus = "idle";
  let wanted = false; // does the app want a connection right now?
  let attempt = 0;
  let current: SocketLike | null = null;
  let timer: unknown = null;
  let generation = 0; // identifies the latest attempt; older sockets are ignored

  function setStatus(next: SocketStatus) {
    status = next;
    options.onStatus?.(next);
  }

  function scheduleRetry() {
    setStatus("waiting");
    const delay = backoffDelay(attempt, baseMs, maxMs, random);
    attempt += 1;
    timer = timers.set(connect, delay);
  }

  async function connect() {
    if (!wanted) return;
    const mine = ++generation;
    setStatus("connecting");

    let url: string;
    try {
      url = await options.getUrl();
    } catch {
      if (mine === generation) scheduleRetry(); // e.g. offline: the ticket request failed
      return;
    }
    if (!wanted || mine !== generation) return;

    const ws = factory(url);
    current = ws;
    ws.onopen = () => {
      if (mine !== generation) return;
      attempt = 0; // a good connection earns a fresh start
      setStatus("open");
    };
    ws.onmessage = (event) => {
      if (mine !== generation) return;
      let parsed: unknown;
      try {
        parsed = JSON.parse(String(event.data));
      } catch {
        return; // not JSON: ignore it rather than crash
      }
      options.onMessage(parsed);
    };
    ws.onerror = () => {}; // onclose always follows an error, and does the work
    ws.onclose = (event) => {
      if (mine !== generation) return; // a late event from a socket we already replaced
      current = null;
      if (!wanted) return;
      if (FATAL_CLOSE_CODES.has(event.code)) {
        wanted = false;
        setStatus("stopped");
        return;
      }
      scheduleRetry();
    };
  }

  return {
    get status() {
      return status;
    },

    start() {
      if (wanted && status !== "stopped") return;
      wanted = true;
      void connect();
    },

    stop() {
      wanted = false;
      generation += 1; // everything the old socket says from now on is ignored
      if (timer !== null) timers.clear(timer);
      timer = null;
      current?.close(1000);
      current = null;
      attempt = 0;
      setStatus("idle");
    },

    // The app came back to the foreground: do not wait out the back-off.
    reconnectNow() {
      if (!wanted || status !== "waiting") return;
      if (timer !== null) timers.clear(timer);
      timer = null;
      attempt = 0;
      void connect();
    },
  };
}

export type ReconnectingSocket = ReturnType<typeof createSocket>;
