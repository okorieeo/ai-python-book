// A WebSocket client that survives bad networks. It knows nothing about React or chat.

export type ConnectionStatus = "idle" | "connecting" | "open" | "reconnecting" | "closed";

/** Throw this from getTicket() when retrying cannot help (for example: logged out). */
export class FatalSocketError extends Error {}

/** The small part of the browser WebSocket we use. Tests supply a fake. */
export interface WebSocketLike {
  readonly readyState: number;
  send(data: string): void;
  close(code?: number, reason?: string): void;
  onopen: ((event: unknown) => void) | null;
  onmessage: ((event: { data: unknown }) => void) | null;
  onclose: ((event: { code: number }) => void) | null;
  onerror: ((event: unknown) => void) | null;
}

export interface SocketOptions {
  url: string; // for example wss://api.example.com/ws/chat/
  getTicket: () => Promise<string>; // asks the backend for a short-lived, single-use ticket
  onMessage: (data: unknown) => void;
  onStatus?: (status: ConnectionStatus) => void;
  pingMessage?: string; // what to send as a heartbeat
  heartbeatMs?: number; // how often to check the connection is alive
  pongTimeoutMs?: number; // how long to wait for ANY message after a ping
  baseDelayMs?: number; // first reconnect delay ceiling
  maxDelayMs?: number; // reconnect delays never exceed this
  stableMs?: number; // an open connection this old counts as healthy
  fatalCloseCodes?: number[]; // close codes after which we must NOT reconnect
  // Injection points, so tests need neither a network nor real time:
  createSocket?: (url: string) => WebSocketLike;
  setTimer?: (fn: () => void, ms: number) => unknown;
  clearTimer?: (handle: unknown) => void;
  random?: () => number;
}

const OPEN = 1; // WebSocket.OPEN

/** "Full jitter": a random delay between 0 and min(max, base * 2^attempt). */
export function backoffDelay(
  attempt: number,
  baseMs: number,
  maxMs: number,
  random: () => number = Math.random,
): number {
  const ceiling = Math.min(maxMs, baseMs * 2 ** attempt);
  return Math.floor(random() * ceiling);
}

export class ReconnectingSocket {
  private status: ConnectionStatus = "idle";
  private ws: WebSocketLike | null = null;
  // Bumps on every new attempt and on disconnect, so stale events can be ignored.
  private generation = 0;
  private attempt = 0;
  private retryTimer: unknown = null;
  private heartbeatTimer: unknown = null;
  private pongTimer: unknown = null;
  private stableTimer: unknown = null;
  private readonly o: Required<Omit<SocketOptions, "onStatus">> &
    Pick<SocketOptions, "onStatus">;

  constructor(options: SocketOptions) {
    this.o = {
      pingMessage: '{"type":"ping"}',
      heartbeatMs: 25_000,
      pongTimeoutMs: 10_000,
      baseDelayMs: 500,
      maxDelayMs: 30_000,
      stableMs: 10_000,
      fatalCloseCodes: [1008, 4403],
      createSocket: (url) => new WebSocket(url) as unknown as WebSocketLike,
      setTimer: (fn, ms) => setTimeout(fn, ms),
      clearTimer: (handle) => clearTimeout(handle as ReturnType<typeof setTimeout>),
      random: Math.random,
      ...options,
    };
  }

  get currentStatus(): ConnectionStatus {
    return this.status;
  }

  /** Start connecting. Safe to call twice (React StrictMode does). */
  connect(): void {
    if (this.status === "connecting" || this.status === "open") return;
    this.attempt = 0;
    this.begin();
  }

  /** Stop for good. Pending tickets and timers are cancelled. */
  disconnect(): void {
    this.generation++; // everything still in flight becomes stale
    this.clearAllTimers();
    this.detach(1000, "client disconnect");
    this.setStatus("closed");
  }

  /** Returns true if the message was handed to the socket. It is never queued. */
  send(data: string): boolean {
    if (this.status !== "open" || this.ws?.readyState !== OPEN) return false;
    this.ws.send(data);
    return true;
  }

  /** The tab became visible or the network came back: do not wait for the timer. */
  nudge(): void {
    if (this.status === "reconnecting") {
      this.o.clearTimer(this.retryTimer);
      this.attempt = 0;
      this.begin();
    } else if (this.status === "open") {
      this.sendPing(); // finds a dead connection in seconds, not minutes
    }
  }

  // ---------------------------------------------------------------- internals

  private begin(): void {
    const generation = ++this.generation;
    this.setStatus(this.attempt === 0 ? "connecting" : "reconnecting");
    this.o
      .getTicket()
      .then((ticket) => {
        if (generation !== this.generation) return; // disconnected meanwhile
        this.open(ticket, generation);
      })
      .catch((error: unknown) => {
        if (generation !== this.generation) return;
        if (error instanceof FatalSocketError) this.setStatus("closed");
        else this.scheduleReconnect();
      });
  }

  private open(ticket: string, generation: number): void {
    const separator = this.o.url.includes("?") ? "&" : "?";
    const ticketParam = `ticket=${encodeURIComponent(ticket)}`;
    const ws = this.o.createSocket(`${this.o.url}${separator}${ticketParam}`);
    this.ws = ws;
    ws.onopen = () => {
      if (generation !== this.generation) return;
      this.setStatus("open");
      this.stableTimer = this.o.setTimer(() => (this.attempt = 0), this.o.stableMs);
      this.heartbeatTimer = this.o.setTimer(() => this.heartbeat(), this.o.heartbeatMs);
    };
    ws.onmessage = (event) => {
      if (generation !== this.generation) return;
      this.o.clearTimer(this.pongTimer); // ANY message proves the connection is alive
      this.pongTimer = null;
      this.o.onMessage(event.data);
    };
    ws.onerror = () => {
      if (generation !== this.generation) return;
      // Browsers send "error" and then "close". Some runtimes (Node, for a refused
      // connection) send only "error". If we never got open, treat it as lost now.
      // connectionLost() makes any later close event stale, so nothing runs twice.
      if (ws.readyState !== OPEN) this.connectionLost(1006);
    };
    ws.onclose = (event) => {
      if (generation !== this.generation) return;
      this.connectionLost(event.code);
    };
  }

  private heartbeat(): void {
    this.sendPing();
    this.heartbeatTimer = this.o.setTimer(() => this.heartbeat(), this.o.heartbeatMs);
  }

  private sendPing(): void {
    if (this.pongTimer !== null || this.ws?.readyState !== OPEN) return;
    this.ws.send(this.o.pingMessage);
    const generation = this.generation;
    this.pongTimer = this.o.setTimer(() => {
      if (generation !== this.generation) return;
      this.connectionLost(4000); // nothing came back: a half-open connection
    }, this.o.pongTimeoutMs);
  }

  private connectionLost(code: number): void {
    this.generation++; // the dead socket's remaining events are now stale
    this.clearAllTimers();
    this.detach(code === 4000 ? 4000 : undefined);
    if (this.o.fatalCloseCodes.includes(code)) this.setStatus("closed");
    else this.scheduleReconnect();
  }

  private scheduleReconnect(): void {
    this.setStatus("reconnecting");
    const { baseDelayMs, maxDelayMs, random } = this.o;
    const delay = backoffDelay(this.attempt, baseDelayMs, maxDelayMs, random);
    this.attempt++;
    this.retryTimer = this.o.setTimer(() => this.begin(), delay);
  }

  /** Detach handlers first, then close, so the old socket cannot call back into us. */
  private detach(code?: number, reason?: string): void {
    const ws = this.ws;
    this.ws = null;
    if (!ws) return;
    ws.onopen = ws.onmessage = ws.onclose = ws.onerror = null;
    try {
      ws.close(code, reason);
    } catch {
      /* already closed */
    }
  }

  private clearAllTimers(): void {
    const handles = [this.retryTimer, this.heartbeatTimer, this.pongTimer, this.stableTimer];
    for (const handle of handles) {
      if (handle !== null) this.o.clearTimer(handle);
    }
    this.retryTimer = this.heartbeatTimer = this.pongTimer = this.stableTimer = null;
  }

  private setStatus(status: ConnectionStatus): void {
    if (this.status === status) return;
    this.status = status;
    this.o.onStatus?.(status);
  }
}
