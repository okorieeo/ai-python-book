import { ApiError, QueueFullError, SessionExpiredError, isRetryable } from "./errors";
import type { KeyValueStore } from "./storage";

export interface QueuedRequest {
  id: string;
  method: "POST" | "PUT" | "PATCH" | "DELETE";
  path: string;
  body?: unknown;
  /** Sent with every attempt, so the server can ignore a repeat of something it already did. */
  idempotencyKey: string;
  /** A newer item with the same dedupeKey replaces an older one still waiting (last write wins). */
  dedupeKey?: string;
  createdAt: number;
  attempts: number;
  status: "pending" | "failed";
  lastError?: { status?: number; code: string; message: string };
}

export interface RequestSender {
  request<T>(method: string, path: string, opts?: { body?: unknown; idempotencyKey?: string }): Promise<T>;
}

export interface QueueOptions {
  storage: KeyValueStore;
  client: RequestSender;
  isOnline?: () => boolean;
  now?: () => number;
  makeId?: () => string;
  maxAttempts?: number;
  maxItems?: number;
  storageKey?: string;
  /** Called if saved data could not be read. The queue starts empty instead of crashing the app. */
  onCorrupt?: () => void;
}

export interface FlushResult {
  sent: number;
  failed: number;
  remaining: number;
  stoppedBecause: "done" | "offline" | "network" | "signed-out";
}

let counter = 0;
const defaultId = () => `q_${Date.now().toString(36)}_${(counter++).toString(36)}_${Math.random().toString(36).slice(2, 8)}`;

/**
 * Writes the user makes while offline (a new note, a rename) wait here, are saved to storage so they
 * survive the app being closed, and are sent in order when the connection returns.
 * Only changes go here. Reading data uses the normal client and a cache.
 */
export class OfflineQueue {
  private items: QueuedRequest[] = [];
  private loaded = false;
  private flushing: Promise<FlushResult> | null = null;
  private inFlightId: string | null = null;
  private readonly listeners = new Set<() => void>();
  private readonly key: string;

  constructor(private readonly o: QueueOptions) {
    this.key = o.storageKey ?? "offline.queue.v1";
  }

  async load(): Promise<void> {
    if (this.loaded) return;
    this.loaded = true;
    const raw = await this.o.storage.getItem(this.key);
    if (raw === null) return;
    try {
      const parsed = JSON.parse(raw) as { v?: number; items?: unknown };
      if (parsed.v === 1 && Array.isArray(parsed.items) && parsed.items.every(isQueued)) {
        this.items = parsed.items as QueuedRequest[];
        return;
      }
    } catch {
      /* fall through */
    }
    this.o.onCorrupt?.();
    this.items = [];
    await this.save();
  }

  pending(): QueuedRequest[] {
    return this.items.filter((i) => i.status === "pending");
  }
  failed(): QueuedRequest[] {
    return this.items.filter((i) => i.status === "failed");
  }

  subscribe(listener: () => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  async enqueue(input: {
    method: QueuedRequest["method"];
    path: string;
    body?: unknown;
    dedupeKey?: string;
    idempotencyKey?: string;
  }): Promise<QueuedRequest> {
    await this.load();
    if (input.dedupeKey) {
      this.items = this.items.filter(
        (i) => !(i.status === "pending" && i.dedupeKey === input.dedupeKey && i.id !== this.inFlightId),
      );
    }
    if (this.items.length >= (this.o.maxItems ?? 200)) throw new QueueFullError(this.o.maxItems ?? 200);
    const id = (this.o.makeId ?? defaultId)();
    const item: QueuedRequest = {
      id,
      method: input.method,
      path: input.path,
      body: input.body,
      dedupeKey: input.dedupeKey,
      idempotencyKey: input.idempotencyKey ?? `idem_${id}`,
      createdAt: (this.o.now ?? Date.now)(),
      attempts: 0,
      status: "pending",
    };
    this.items.push(item);
    await this.save();
    return item;
  }

  /** Put a failed item back in line (for example after the user fixed the problem). */
  async retry(id: string): Promise<void> {
    await this.load();
    const item = this.items.find((i) => i.id === id && i.status === "failed");
    if (item) {
      item.status = "pending";
      item.attempts = 0;
      item.lastError = undefined;
      await this.save();
    }
  }

  async discard(id: string): Promise<void> {
    await this.load();
    this.items = this.items.filter((i) => i.id !== id);
    await this.save();
  }

  /** Send everything that is waiting, in order. Safe to call often: overlapping calls share one run. */
  flush(): Promise<FlushResult> {
    if (!this.flushing) {
      this.flushing = this.runFlush().finally(() => {
        this.flushing = null;
      });
    }
    return this.flushing;
  }

  private async runFlush(): Promise<FlushResult> {
    await this.load();
    const result: FlushResult = { sent: 0, failed: 0, remaining: 0, stoppedBecause: "done" };
    if (this.o.isOnline && !this.o.isOnline()) {
      result.stoppedBecause = "offline";
      result.remaining = this.pending().length;
      return result;
    }
    for (const item of [...this.pending()].sort((a, b) => a.createdAt - b.createdAt)) {
      if (!this.items.includes(item)) continue; // replaced or discarded while we were busy
      this.inFlightId = item.id;
      try {
        await this.o.client.request(item.method, item.path, { body: item.body, idempotencyKey: item.idempotencyKey });
        this.items = this.items.filter((i) => i !== item);
        result.sent++;
      } catch (error) {
        item.attempts++;
        if (error instanceof SessionExpiredError) {
          result.stoppedBecause = "signed-out";
          break; // keep everything: it can be sent after the user signs in again
        }
        if (isRetryable(error)) {
          if (item.attempts >= (this.o.maxAttempts ?? 5)) {
            item.status = "failed";
            item.lastError = describe(error);
            result.failed++;
          } else {
            result.stoppedBecause = "network";
            await this.save();
            break; // stop: do not hammer a struggling server, and keep the order
          }
        } else {
          item.status = "failed"; // the server said no (400, 403, 404, 409, 422): retrying cannot help
          item.lastError = describe(error);
          result.failed++;
        }
      } finally {
        this.inFlightId = null;
        await this.save();
      }
    }
    result.remaining = this.pending().length;
    return result;
  }

  private async save(): Promise<void> {
    await this.o.storage.setItem(this.key, JSON.stringify({ v: 1, items: this.items }));
    for (const l of this.listeners) l();
  }
}

function describe(error: unknown): NonNullable<QueuedRequest["lastError"]> {
  if (error instanceof ApiError) return { status: error.status, code: error.code, message: error.message };
  const e = error as Error;
  return { code: e?.name ?? "error", message: e?.message ?? "Unknown error" };
}

function isQueued(x: unknown): x is QueuedRequest {
  if (typeof x !== "object" || x === null) return false;
  const i = x as Record<string, unknown>;
  return (
    typeof i.id === "string" &&
    typeof i.method === "string" &&
    typeof i.path === "string" &&
    typeof i.idempotencyKey === "string" &&
    typeof i.createdAt === "number" &&
    typeof i.attempts === "number" &&
    (i.status === "pending" || i.status === "failed")
  );
}
