import { backoffDelay, type BackoffOptions } from './retry';

export interface ReconnectOptions extends BackoffOptions {
  /** Give up after this many failed attempts in a row (default 10). */
  maxAttempts?: number;
}

/** Counts failed attempts and hands out the next jittered delay, or null when it is time to give up. */
export class ReconnectPolicy {
  private attempts = 0;
  constructor(private readonly options: ReconnectOptions = {}) {}

  nextDelay(): number | null {
    if (this.attempts >= (this.options.maxAttempts ?? 10)) return null;
    return backoffDelay(this.attempts++, this.options);
  }
  reset(): void {
    this.attempts = 0;
  }
  get attemptCount(): number {
    return this.attempts;
  }
}

export type SocketStatus = 'connecting' | 'open' | 'reconnecting' | 'offline' | 'closed' | 'gave-up';

/**
 * The small part of the WebSocket API we use, so tests can pass a fake. The handler parameters are
 * `any` on purpose: it lets the real WebSocket (whose events are MessageEvent and Event) and a
 * simple fake both fit without casts.
 */
export interface SocketLike {
  onopen: ((event: any) => void) | null;
  onclose: ((event: any) => void) | null;
  onerror: ((event: any) => void) | null;
  onmessage: ((event: any) => void) | null;
  send(data: string): void;
  close(code?: number): void;
}

export interface ReconnectingSocketOptions {
  createSocket: () => SocketLike;
  onMessage: (data: unknown) => void;
  onStatus?: (status: SocketStatus) => void;
  policy?: ReconnectPolicy;
  /** A connection must stay up this long before we forget earlier failures (stops flapping). */
  stableAfterMs?: number;
  setTimeoutFn?: (fn: () => void, ms: number) => ReturnType<typeof setTimeout>;
  clearTimeoutFn?: (id: ReturnType<typeof setTimeout>) => void;
}

/**
 * Keeps one WebSocket alive: reconnects with backoff, pauses while the phone is offline,
 * resumes at once when the network returns, and ignores events from sockets it already replaced.
 */
export class ReconnectingSocket {
  private socket: SocketLike | null = null;
  private wantOpen = false;
  private online = true;
  private retryTimer: ReturnType<typeof setTimeout> | null = null;
  private stableTimer: ReturnType<typeof setTimeout> | null = null;
  private readonly policy: ReconnectPolicy;
  private readonly stableAfterMs: number;
  private readonly setT: NonNullable<ReconnectingSocketOptions['setTimeoutFn']>;
  private readonly clearT: NonNullable<ReconnectingSocketOptions['clearTimeoutFn']>;
  status: SocketStatus = 'closed';

  constructor(private readonly options: ReconnectingSocketOptions) {
    this.policy = options.policy ?? new ReconnectPolicy();
    this.stableAfterMs = options.stableAfterMs ?? 10_000;
    this.setT = options.setTimeoutFn ?? ((fn, ms) => setTimeout(fn, ms));
    this.clearT = options.clearTimeoutFn ?? ((id) => clearTimeout(id));
  }

  start(): void {
    this.wantOpen = true;
    this.connect();
  }

  stop(): void {
    this.wantOpen = false;
    this.clearTimers();
    this.dropSocket();
    this.setStatus('closed');
  }

  /** Call with NetInfo's verdict (see isOnline). */
  setOnline(online: boolean): void {
    if (online === this.online) return;
    this.online = online;
    if (!this.wantOpen) return;
    if (!online) {
      this.clearTimers();
      this.dropSocket();
      this.setStatus('offline');
    } else {
      this.policy.reset();
      this.connect();
    }
  }

  send(data: string): boolean {
    if (this.status !== 'open' || !this.socket) return false;
    this.socket.send(data);
    return true;
  }

  private connect(): void {
    this.clearTimers();
    this.dropSocket();
    if (!this.wantOpen) return;
    if (!this.online) return this.setStatus('offline');

    this.setStatus(this.policy.attemptCount === 0 ? 'connecting' : 'reconnecting');
    const socket = this.options.createSocket();
    this.socket = socket;

    socket.onopen = () => {
      if (socket !== this.socket) return;
      this.setStatus('open');
      this.stableTimer = this.setT(() => this.policy.reset(), this.stableAfterMs);
    };
    socket.onmessage = (event) => {
      if (socket === this.socket) this.options.onMessage(event.data);
    };
    socket.onclose = () => {
      if (socket !== this.socket) return;
      this.socket = null;
      if (this.stableTimer) this.clearT(this.stableTimer);
      this.stableTimer = null;
      this.scheduleReconnect();
    };
    socket.onerror = () => {
      // A close event always follows; the reconnect is scheduled there.
    };
  }

  private scheduleReconnect(): void {
    if (!this.wantOpen || !this.online) return;
    const delay = this.policy.nextDelay();
    if (delay === null) return this.setStatus('gave-up');
    this.setStatus('reconnecting');
    this.retryTimer = this.setT(() => this.connect(), delay);
  }

  private dropSocket(): void {
    const socket = this.socket;
    this.socket = null; // forget it first so its close event is ignored
    if (socket) {
      socket.onopen = socket.onclose = socket.onerror = socket.onmessage = null;
      try {
        socket.close(1000);
      } catch {
        /* already closed */
      }
    }
  }

  private clearTimers(): void {
    if (this.retryTimer) this.clearT(this.retryTimer);
    if (this.stableTimer) this.clearT(this.stableTimer);
    this.retryTimer = this.stableTimer = null;
  }

  private setStatus(status: SocketStatus): void {
    if (this.status === status) return;
    this.status = status;
    this.options.onStatus?.(status);
  }
}
