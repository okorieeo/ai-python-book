export interface WebSocketLike {
  readyState: number;
  send(data: string): void;
  close(code?: number, reason?: string): void;
  onopen: ((ev: unknown) => void) | null;
  onmessage: ((ev: { data: unknown }) => void) | null;
  onclose: ((ev: { code: number; reason?: string }) => void) | null;
  onerror: ((ev: unknown) => void) | null;
}

export type SocketState = "idle" | "connecting" | "authenticating" | "open" | "waiting" | "paused" | "closed";

export interface SocketOptions {
  url: string;
  getToken: () => Promise<string | null>;
  createSocket?: (url: string) => WebSocketLike;
  /** Schedules fn after ms and returns a function that cancels it. Injected so tests control time. */
  schedule?: (fn: () => void, ms: number) => () => void;
  now?: () => number;
  random?: () => number;
  heartbeatMs?: number;
  pongTimeoutMs?: number;
  authTimeoutMs?: number;
  baseDelayMs?: number;
  maxDelayMs?: number;
  /** A connection must stay up this long before the retry counter resets. */
  stableAfterMs?: number;
  maxQueued?: number;
}

type Listener<T> = (value: T) => void;

/** Close code the server uses for a refused token. Match it to your Channels consumer (Chapter 14). */
export const CLOSE_AUTH_FAILED = 4401;

const defaultSchedule = (fn: () => void, ms: number) => {
  const handle = setTimeout(fn, ms);
  return () => clearTimeout(handle);
};

/**
 * A WebSocket that looks after itself on a phone, where connections drop all the time:
 *  - the token is sent as the FIRST MESSAGE, never in the URL (URLs end up in server logs);
 *  - it reconnects with growing, randomised delays, and stops if the token is refused;
 *  - it sends its own ping and reconnects if no pong comes back (a dead connection can look open);
 *  - messages sent while disconnected wait in a small queue;
 *  - pause() and resume() are for the app going to the background and back.
 *
 * The messages it assumes (adapt them to your server): {"type":"auth","token":...} answered by
 * {"type":"auth_ok"}, and {"type":"ping"} answered by {"type":"pong"}.
 */
export class SocketManager {
  private socket: WebSocketLike | null = null;
  private generation = 0;
  private attempt = 0;
  private openedAt = 0;
  private online = true;
  private wantConnected = false;
  private state: SocketState = "idle";
  private queue: string[] = [];
  private cancelTimers: Array<() => void> = [];
  private readonly stateListeners = new Set<Listener<SocketState>>();
  private readonly messageListeners = new Set<Listener<unknown>>();
  private readonly authFailedListeners = new Set<Listener<void>>();

  constructor(private readonly o: SocketOptions) {}

  getState(): SocketState {
    return this.state;
  }
  onState(fn: Listener<SocketState>): () => void {
    this.stateListeners.add(fn);
    return () => this.stateListeners.delete(fn);
  }
  onMessage(fn: Listener<unknown>): () => void {
    this.messageListeners.add(fn);
    return () => this.messageListeners.delete(fn);
  }
  onAuthFailed(fn: Listener<void>): () => void {
    this.authFailedListeners.add(fn);
    return () => this.authFailedListeners.delete(fn);
  }

  connect(): void {
    this.wantConnected = true;
    if (this.state === "connecting" || this.state === "authenticating" || this.state === "open") return;
    this.attempt = this.state === "closed" ? 0 : this.attempt;
    void this.open();
  }

  /** Returns false if the message was dropped because the queue is full. */
  send(message: unknown): boolean {
    const text = JSON.stringify(message);
    if (this.state === "open" && this.socket) {
      this.socket.send(text);
      return true;
    }
    if (this.queue.length >= (this.o.maxQueued ?? 50)) return false;
    this.queue.push(text);
    return true;
  }

  close(): void {
    this.wantConnected = false;
    this.teardown(1000, "client closed");
    this.setState("closed");
  }

  pause(): void {
    this.teardown(1000, "paused");
    this.setState("paused");
  }

  resume(): void {
    if (this.wantConnected && this.state === "paused") {
      this.attempt = 0;
      void this.open();
    }
  }

  setOnline(online: boolean): void {
    this.online = online;
    if (online && this.wantConnected && (this.state === "waiting" || this.state === "idle")) {
      this.cancelAll();
      void this.open();
    }
  }

  // ------------------------------------------------------------------ internals
  private schedule(fn: () => void, ms: number): void {
    const cancel = (this.o.schedule ?? defaultSchedule)(fn, ms);
    this.cancelTimers.push(cancel);
  }

  private cancelAll(): void {
    for (const c of this.cancelTimers) c();
    this.cancelTimers = [];
  }

  private setState(state: SocketState): void {
    if (state === this.state) return;
    this.state = state;
    for (const l of this.stateListeners) l(state);
  }

  private teardown(code: number, reason: string): void {
    this.generation++; // events from the old socket are now ignored
    this.cancelAll();
    const s = this.socket;
    this.socket = null;
    if (s) {
      s.onopen = s.onmessage = s.onclose = s.onerror = null;
      try {
        s.close(code, reason);
      } catch {
        /* already closed */
      }
    }
  }

  private async open(): Promise<void> {
    if (!this.online) {
      this.setState("waiting");
      return;
    }
    this.teardown(1000, "reconnecting");
    const generation = this.generation;
    this.setState("connecting");
    const socket = (this.o.createSocket ?? ((url: string) => new (globalThis as unknown as { WebSocket: new (u: string) => WebSocketLike }).WebSocket(url)))(this.o.url);
    this.socket = socket;
    socket.onopen = () => {
      if (generation !== this.generation) return;
      void this.authenticate(socket, generation);
    };
    socket.onmessage = (ev) => {
      if (generation !== this.generation) return;
      this.handleMessage(ev.data, socket, generation);
    };
    socket.onclose = (ev) => {
      if (generation !== this.generation) return;
      this.handleClosed(ev.code);
    };
    socket.onerror = () => {
      /* a close event follows; reconnecting is handled there */
    };
  }

  private async authenticate(socket: WebSocketLike, generation: number): Promise<void> {
    this.setState("authenticating");
    const token = await this.o.getToken();
    if (generation !== this.generation) return;
    if (!token) {
      this.teardown(1000, "no token");
      this.setState("closed");
      this.wantConnected = false;
      for (const l of this.authFailedListeners) l();
      return;
    }
    socket.send(JSON.stringify({ type: "auth", token }));
    this.schedule(() => {
      if (generation === this.generation && this.state === "authenticating") this.handleClosed(4000);
    }, this.o.authTimeoutMs ?? 10_000);
  }

  private handleMessage(data: unknown, socket: WebSocketLike, generation: number): void {
    let message: unknown;
    try {
      message = typeof data === "string" ? JSON.parse(data) : null;
    } catch {
      return; // ignore anything that is not JSON
    }
    // Only objects with a text "type" count as messages. Anything else is noise or an attack.
    if (typeof message !== "object" || message === null || typeof (message as { type?: unknown }).type !== "string") return;
    const type = (message as { type: string }).type;
    if (type === "auth_ok") {
      this.cancelAll();
      this.openedAt = (this.o.now ?? Date.now)();
      this.setState("open");
      for (const queued of this.queue.splice(0)) socket.send(queued);
      this.scheduleHeartbeat(socket, generation);
      return;
    }
    if (type === "pong") {
      this.cancelAll();
      this.scheduleHeartbeat(socket, generation);
      return;
    }
    if (this.state !== "open") return; // nothing is trusted before authentication succeeds
    for (const l of this.messageListeners) l(message);
  }

  private scheduleHeartbeat(socket: WebSocketLike, generation: number): void {
    this.schedule(() => {
      if (generation !== this.generation || this.state !== "open") return;
      socket.send(JSON.stringify({ type: "ping" }));
      this.schedule(() => {
        if (generation === this.generation && this.state === "open") this.handleClosed(4000); // no pong
      }, this.o.pongTimeoutMs ?? 10_000);
    }, this.o.heartbeatMs ?? 25_000);
  }

  private handleClosed(code: number): void {
    const wasStable = this.state === "open" && (this.o.now ?? Date.now)() - this.openedAt >= (this.o.stableAfterMs ?? 10_000);
    this.teardown(1000, "closed");
    if (code === CLOSE_AUTH_FAILED) {
      this.wantConnected = false;
      this.setState("closed");
      for (const l of this.authFailedListeners) l(); // refresh the token, then call connect() again
      return;
    }
    if (!this.wantConnected) {
      this.setState("closed");
      return;
    }
    if (wasStable) this.attempt = 0;
    const base = this.o.baseDelayMs ?? 1_000;
    const ceiling = Math.min(this.o.maxDelayMs ?? 30_000, base * 2 ** this.attempt);
    const delay = Math.round(ceiling / 2 + (ceiling / 2) * (this.o.random ?? Math.random)());
    this.attempt++;
    this.setState("waiting");
    this.schedule(() => {
      if (this.wantConnected && this.state === "waiting") void this.open();
    }, delay);
  }
}
