/** Errors the rest of the app can tell apart. A screen should react differently to each. */

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly details?: unknown,
    readonly retryAfterMs?: number,
  ) {
    super(message);
    this.name = "ApiError";
    Object.setPrototypeOf(this, new.target.prototype);
  }

  /** Worth trying again later: the server is busy or briefly unavailable. */
  get retryable(): boolean {
    return this.status === 408 || this.status === 429 || (this.status >= 502 && this.status <= 504);
  }
}

/** No answer at all: offline, DNS, a dropped connection. */
export class NetworkError extends Error {
  readonly retryable = true;
  constructor(message = "The network request failed") {
    super(message);
    this.name = "NetworkError";
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

export class TimeoutError extends Error {
  readonly retryable = true;
  constructor(message = "The request took too long") {
    super(message);
    this.name = "TimeoutError";
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

/** The refresh token was refused. The user must sign in again. */
export class SessionExpiredError extends Error {
  readonly retryable = false;
  constructor(message = "Your session has expired") {
    super(message);
    this.name = "SessionExpiredError";
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

export class QueueFullError extends Error {
  constructor(max: number) {
    super(`The offline queue is full (${max} items)`);
    this.name = "QueueFullError";
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

export function isRetryable(error: unknown): boolean {
  return (
    (error instanceof ApiError && error.retryable) ||
    error instanceof NetworkError ||
    error instanceof TimeoutError
  );
}
