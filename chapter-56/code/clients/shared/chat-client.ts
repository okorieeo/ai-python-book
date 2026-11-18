import { CLOSE_UNAUTHORIZED, type ClientFrame, type ServerFrame } from "./chat-protocol";
import type { ConnectionStatus } from "./chat-state";

/** The few WebSocket members we use; the browser's and React Native's WebSocket both satisfy it. */
export interface SocketLike {
  send(data: string): void;
  close(code?: number): void;
  onopen: ((ev: unknown) => void) | null;
  onmessage: ((ev: { data: unknown }) => void) | null;
  onclose: ((ev: { code: number }) => void) | null;
  onerror: ((ev: unknown) => void) | null;
}

export class UnauthorizedError extends Error {}

export type ChatClientOptions = {
  wsUrl: string;
  /** Called before EVERY (re)connect: tickets are single-use and expire after 60 seconds. */
  getTicket: () => Promise<string>;
  onFrame: (frame: ServerFrame) => void;
  onStatus: (status: ConnectionStatus) => void;
  /** The ticket was refused (login expired). Refresh the token, then call connect() again. */
  onUnauthorized?: () => void;
  createSocket?: (url: string) => SocketLike;
  baseDelayMs?: number;
  maxDelayMs?: number;
  random?: () => number;
  setTimer?: (fn: () => void, ms: number) => () => void; // returns a cancel function
};

export class ChatClient {
  private socket: SocketLike | null = null;
  private attempt = 0;
  private cancelTimer: (() => void) | null = null;
  private stopped = true;
  private connecting = false;

  constructor(private readonly o: ChatClientOptions) {}

  connect(): void {
    if (this.connecting || this.socket) return; // idempotent: React effects may call this twice
    this.stopped = false;
    void this.open();
  }

  send(frame: ClientFrame): boolean {
    if (!this.socket) return false;
    this.socket.send(JSON.stringify(frame));
    return true;
  }

  close(): void {
    this.stopped = true;
    this.cancelTimer?.();
    this.cancelTimer = null;
    const socket = this.socket;
    this.socket = null;
    socket?.close(1000);
  }

  /** Delay before reconnect attempt number `attempt`: exponential, capped, with jitter so clients do not stampede. */
  delayFor(attempt: number): number {
    const base = this.o.baseDelayMs ?? 500;
    const cap = this.o.maxDelayMs ?? 15_000;
    const random = this.o.random ?? Math.random;
    return Math.min(cap, base * 2 ** attempt) * (0.5 + random() / 2);
  }

  private async open(): Promise<void> {
    this.connecting = true;
    this.o.onStatus("connecting");
    let ticket: string;
    try {
      ticket = await this.o.getTicket();
    } catch (err) {
      this.connecting = false;
      if (err instanceof UnauthorizedError) {
        this.stopped = true;
        this.o.onStatus("closed");
        this.o.onUnauthorized?.();
      } else {
        this.scheduleReconnect();
      }
      return;
    }
    this.connecting = false;
    if (this.stopped) return; // close() was called while we waited for the ticket

    const create = this.o.createSocket ?? ((url: string) => new WebSocket(url) as unknown as SocketLike);
    const socket = create(`${this.o.wsUrl}?ticket=${encodeURIComponent(ticket)}`);
    this.socket = socket;

    socket.onopen = () => this.o.onStatus("open");
    socket.onmessage = (ev) => {
      let frame: ServerFrame;
      try {
        frame = JSON.parse(String(ev.data)) as ServerFrame;
      } catch {
        return; // ignore garbage instead of crashing the UI
      }
      if (frame.type === "ready") this.attempt = 0; // a healthy connection resets the backoff
      this.o.onFrame(frame);
    };
    socket.onerror = () => undefined; // onclose always follows and does the work
    socket.onclose = (ev) => {
      if (this.socket !== socket) return; // an old socket closing after we replaced it
      this.socket = null;
      this.o.onStatus("closed");
      if (this.stopped) return;
      if (ev.code === CLOSE_UNAUTHORIZED) {
        this.stopped = true;
        this.o.onUnauthorized?.();
        return;
      }
      this.scheduleReconnect();
    };
  }

  private scheduleReconnect(): void {
    const delay = this.delayFor(this.attempt++);
    const set = this.o.setTimer ?? ((fn, ms) => { const id = setTimeout(fn, ms); return () => clearTimeout(id); });
    this.cancelTimer = set(() => { this.cancelTimer = null; if (!this.stopped) void this.open(); }, delay);
  }
}
