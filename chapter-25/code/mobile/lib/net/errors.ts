/**
 * The failures a mobile client has to tell apart. Each one needs a different reaction,
 * so we turn every low-level failure into one of these five kinds.
 */
export type ApiErrorKind = 'network' | 'timeout' | 'aborted' | 'http' | 'parse';

export interface ApiErrorInit {
  kind: ApiErrorKind;
  message?: string;
  status?: number;
  retryAfterMs?: number;
  body?: unknown;
  cause?: unknown;
}

export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly status?: number;
  readonly retryAfterMs?: number;
  readonly body?: unknown;
  readonly cause?: unknown;

  constructor(init: ApiErrorInit) {
    super(init.message ?? defaultMessage(init));
    this.name = 'ApiError';
    this.kind = init.kind;
    this.status = init.status;
    this.retryAfterMs = init.retryAfterMs;
    this.body = init.body;
    this.cause = init.cause;
  }
}

function defaultMessage({ kind, status }: ApiErrorInit): string {
  switch (kind) {
    case 'network':
      return 'Network request failed';
    case 'timeout':
      return 'The request took too long';
    case 'aborted':
      return 'The request was cancelled';
    case 'parse':
      return 'The server sent a response the app could not read';
    case 'http':
      return `The server answered with status ${status ?? 'unknown'}`;
  }
}

/** Statuses that mean "try again later" rather than "your request is wrong". */
const RETRYABLE_STATUS = new Set([408, 429, 500, 502, 503, 504]);

/**
 * May the client repeat this request automatically?
 * Only when repeating is safe (`idempotent`). A timed-out POST may already have been processed.
 */
export function isRetryable(error: unknown, { idempotent }: { idempotent: boolean }): boolean {
  if (!idempotent || !(error instanceof ApiError)) return false;
  switch (error.kind) {
    case 'network':
    case 'timeout':
      return true;
    case 'http':
      return RETRYABLE_STATUS.has(error.status ?? 0);
    default:
      return false;
  }
}

export const isUnauthorized = (error: unknown): boolean =>
  error instanceof ApiError && error.kind === 'http' && error.status === 401;

/** Plain-language text for the screen. Never shows status codes, stack traces or server text. */
export function userMessage(error: unknown): string {
  if (!(error instanceof ApiError)) return 'Something went wrong. Please try again.';
  switch (error.kind) {
    case 'network':
      return 'You seem to be offline. We will try again when you are back online.';
    case 'timeout':
      return 'The connection is slow right now. Please try again.';
    case 'aborted':
      return 'Cancelled.';
    case 'parse':
      return 'We got an unexpected answer from the server. Please try again.';
    case 'http':
      if (error.status === 401) return 'Please sign in again.';
      if (error.status === 403) return 'You do not have access to this.';
      if (error.status === 404) return 'We could not find that. It may have been deleted.';
      if (error.status === 429) return 'You are going a little fast. Please wait a moment.';
      if ((error.status ?? 0) >= 500) return 'Our servers are having a problem. Please try again soon.';
      return 'That did not work. Please check what you entered and try again.';
  }
}
