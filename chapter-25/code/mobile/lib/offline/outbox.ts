import { ApiError, isRetryable, userMessage } from '../net/errors';
import { backoffDelay, type BackoffOptions } from '../net/retry';
import type { KeyValueStorage } from './storage';

export type OutboxStatus = 'pending' | 'failed';

export interface OutboxItem {
  /** Also the idempotency key: the server sees this id on every attempt and creates the thing once. */
  id: string;
  kind: string;
  /** Items in the same scope are sent in order (for chat: the conversation id). */
  scope: string;
  payload: unknown;
  createdAt: number;
  attempts: number;
  nextAttemptAt: number;
  status: OutboxStatus;
  lastError?: string;
}

export type NewOutboxItem = Pick<OutboxItem, 'id' | 'kind' | 'scope' | 'payload'>;

export interface OutboxOptions {
  storage: KeyValueStorage;
  /** Sends one item. Resolve on success; reject with an ApiError on failure. */
  send: (item: OutboxItem) => Promise<unknown>;
  storageKey?: string;
  onSent?: (item: OutboxItem, result: unknown) => void;
  onAuthRequired?: () => void;
  onStorageError?: (error: unknown) => void;
  now?: () => number;
  maxItems?: number;
  maxAttempts?: number;
  maxAgeMs?: number;
  backoff?: BackoffOptions;
}

export class OutboxFullError extends Error {
  constructor(limit: number) {
    super(`The outbox is full (${limit} items).`);
    this.name = 'OutboxFullError';
  }
}

export interface FlushSummary {
  sent: number;
  failed: number;
  pending: number;
  /** Why the run stopped early, if it did. */
  blocked: 'auth' | 'network' | null;
}

type Outcome = 'auth' | 'transient' | 'permanent';

/** Decide what a failure means for a queued item. */
function classify(error: unknown): Outcome {
  if (!(error instanceof ApiError)) return 'permanent'; // a bug in our code: do not loop on it
  if (error.kind === 'http' && error.status === 401) return 'auth';
  if (error.kind === 'parse') return 'transient'; // e.g. a captive portal answered with HTML
  return isRetryable(error, { idempotent: true }) ? 'transient' : 'permanent';
}

const STATUSES = new Set<string>(['pending', 'failed']);

function parseItems(raw: string): OutboxItem[] {
  const data: unknown = JSON.parse(raw);
  const list = (data as { items?: unknown }).items;
  if (!Array.isArray(list)) throw new Error('bad outbox file');
  for (const item of list) {
    const i = item as Record<string, unknown>;
    const ok =
      typeof i.id === 'string' && typeof i.kind === 'string' && typeof i.scope === 'string' &&
      typeof i.createdAt === 'number' && typeof i.attempts === 'number' &&
      typeof i.nextAttemptAt === 'number' && STATUSES.has(String(i.status));
    if (!ok) throw new Error('bad outbox item');
  }
  return list as OutboxItem[];
}

/**
 * A durable queue of writes made while offline. Survives app restarts, keeps order per scope,
 * retries with backoff, and never silently drops a user's work.
 */
export class Outbox {
  private items: OutboxItem[] = [];
  private snapshot: readonly OutboxItem[] = Object.freeze([]);
  private readonly listeners = new Set<() => void>();
  private loaded: Promise<void> | null = null;
  private writeChain: Promise<void> = Promise.resolve();
  private flushing: Promise<FlushSummary> | null = null;
  private rerun = false;

  private readonly key: string;
  private readonly now: () => number;
  private readonly maxItems: number;
  private readonly maxAttempts: number;
  private readonly maxAgeMs: number;

  constructor(private readonly options: OutboxOptions) {
    this.key = options.storageKey ?? 'outbox:v1';
    this.now = options.now ?? Date.now;
    this.maxItems = options.maxItems ?? 100;
    this.maxAttempts = options.maxAttempts ?? 8;
    this.maxAgeMs = options.maxAgeMs ?? 7 * 24 * 60 * 60 * 1000;
  }

  /** Read the saved queue once. Safe to call many times. */
  load(): Promise<void> {
    if (!this.loaded) this.loaded = this.readFromStorage();
    return this.loaded;
  }

  /** For useSyncExternalStore: the same array until something changes. */
  getSnapshot = (): readonly OutboxItem[] => this.snapshot;

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };

  async enqueue(input: NewOutboxItem): Promise<OutboxItem> {
    await this.load();
    const existing = this.items.find((i) => i.id === input.id);
    if (existing) return existing; // same idempotency key: already queued
    if (this.items.length >= this.maxItems) throw new OutboxFullError(this.maxItems);

    const item: OutboxItem = { ...input, createdAt: this.now(), attempts: 0, nextAttemptAt: 0, status: 'pending' };
    this.items = [...this.items, item];
    this.publish();
    try {
      await this.persist();
    } catch (error) {
      this.items = this.items.filter((i) => i.id !== item.id); // not durable, so do not pretend it is queued
      this.publish();
      throw error;
    }
    return item;
  }

  /**
   * Try to send what is due. Calls while a flush is running join it, and anything enqueued
   * in the meantime is picked up by a follow-up pass inside the same run.
   */
  flush(options: { force?: boolean } = {}): Promise<FlushSummary> {
    if (this.flushing) {
      this.rerun = true;
      return this.flushing;
    }
    this.flushing = this.runFlush(options.force ?? false).finally(() => {
      this.flushing = null;
    });
    return this.flushing;
  }

  async retry(id: string): Promise<void> {
    await this.load();
    const item = this.items.find((i) => i.id === id);
    if (!item) return;
    const { lastError: _dropped, ...rest } = item;
    this.replace(id, { ...rest, status: 'pending', attempts: 0, nextAttemptAt: 0 });
    await this.persistQuietly();
  }

  async discard(id: string): Promise<void> {
    await this.load();
    this.items = this.items.filter((i) => i.id !== id);
    this.publish();
    await this.persistQuietly();
  }

  /** Forget everything (sign-out). */
  async clear(): Promise<void> {
    await this.load();
    this.items = [];
    this.publish();
    await this.writeChain.catch(() => undefined);
    await this.options.storage.removeItem(this.key);
  }

  // ---- internals ----

  private async runFlush(force: boolean): Promise<FlushSummary> {
    await this.load();
    let sent = 0;
    let failed = 0;
    let blocked: FlushSummary['blocked'] = null;

    do {
      this.rerun = false;
      const pass = await this.pass(force);
      sent += pass.sent;
      failed += pass.failed;
      blocked = pass.blocked;
    } while (this.rerun && blocked === null);

    return { sent, failed, blocked, pending: this.items.filter((i) => i.status === 'pending').length };
  }

  private async pass(force: boolean): Promise<Omit<FlushSummary, 'pending'>> {
    let sent = 0;
    let failed = 0;

    // Do not send stale surprises: a message queued last month should not appear today.
    for (const item of this.items) {
      if (item.status === 'pending' && this.now() - item.createdAt > this.maxAgeMs) this.fail(item.id, 'Too old to send.');
    }

    const order = this.items.map((i) => i.id);
    const waitingScopes = new Set<string>();

    for (const id of order) {
      const item = this.items.find((i) => i.id === id);
      if (!item || item.status !== 'pending' || waitingScopes.has(item.scope)) continue;
      if (!force && item.nextAttemptAt > this.now()) {
        waitingScopes.add(item.scope); // keep order: later items in this scope wait too
        continue;
      }

      try {
        const result = await this.options.send(item);
        this.items = this.items.filter((i) => i.id !== id);
        this.publish();
        await this.persistQuietly();
        sent++;
        this.options.onSent?.(item, result);
      } catch (error) {
        const outcome = classify(error);
        if (outcome === 'auth') {
          this.options.onAuthRequired?.();
          return { sent, failed, blocked: 'auth' }; // keep the item; it needs a sign-in, not a discard
        }
        if (outcome === 'permanent') {
          this.fail(id, userMessage(error));
          failed++;
          await this.persistQuietly();
          continue;
        }

        const attempts = item.attempts + 1;
        if (attempts >= this.maxAttempts) {
          this.fail(id, 'We could not send this after several tries.');
          failed++;
          await this.persistQuietly();
          continue;
        }
        const retryAfter = error instanceof ApiError ? (error.retryAfterMs ?? 0) : 0;
        const wait = Math.max(backoffDelay(attempts - 1, this.options.backoff), retryAfter);
        this.replace(id, { ...item, attempts, nextAttemptAt: this.now() + wait, lastError: userMessage(error) });
        await this.persistQuietly();

        // A dead network will fail the next items too, and each failure can cost a full timeout.
        if (error instanceof ApiError && (error.kind === 'network' || error.kind === 'timeout')) {
          return { sent, failed, blocked: 'network' };
        }
        waitingScopes.add(item.scope);
      }
    }
    return { sent, failed, blocked: null };
  }

  private fail(id: string, message: string): void {
    const item = this.items.find((i) => i.id === id);
    if (item) this.replace(id, { ...item, status: 'failed', lastError: message });
  }

  private replace(id: string, next: OutboxItem): void {
    this.items = this.items.map((i) => (i.id === id ? next : i));
    this.publish();
  }

  private publish(): void {
    this.snapshot = Object.freeze([...this.items]);
    this.listeners.forEach((listener) => listener());
  }

  /** Writes happen one at a time, in order, so a slow write can never overwrite a newer one. */
  private persist(): Promise<void> {
    const payload = JSON.stringify({ v: 1, items: this.items });
    const write = this.writeChain
      .catch(() => undefined)
      .then(() => this.options.storage.setItem(this.key, payload));
    this.writeChain = write;
    return write;
  }

  private async persistQuietly(): Promise<void> {
    try {
      await this.persist();
    } catch (error) {
      this.options.onStorageError?.(error);
    }
  }

  private async readFromStorage(): Promise<void> {
    const raw = await this.options.storage.getItem(this.key);
    if (raw === null) return;
    try {
      this.items = parseItems(raw);
    } catch {
      // Never crash at startup because of a damaged file. Keep a copy for debugging and start clean.
      await this.options.storage.setItem(`${this.key}:corrupt`, raw).catch(() => undefined);
      this.items = [];
    }
    this.publish();
  }
}
