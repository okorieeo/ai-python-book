// Every failure the app can meet is one of two things:
//   ApiError     the server answered, and said no (4xx / 5xx)
//   NetworkError we never got an answer (offline, timeout, DNS, TLS)
// The difference matters: being offline must never sign the user out.

export type ErrorDetails = Record<string, string[] | string>;

export class ApiError extends Error {
  status: number;
  code: string;
  details?: ErrorDetails;
  requestId?: string;

  constructor(
    status: number,
    code: string,
    message: string,
    details?: ErrorDetails,
    requestId?: string,
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
    this.requestId = requestId;
  }
}

export class NetworkError extends Error {
  timedOut: boolean;

  constructor(message = "Could not reach the server.", timedOut = false) {
    super(message);
    this.name = "NetworkError";
    this.timedOut = timedOut;
  }
}

/** First message per field, ready to show under each input. */
export function fieldErrors(error: unknown): Record<string, string> {
  const out: Record<string, string> = {};
  if (!(error instanceof ApiError) || !error.details) return out;
  for (const [field, value] of Object.entries(error.details)) {
    out[field] = Array.isArray(value) ? (value[0] ?? "") : String(value);
  }
  return out;
}

/** One sentence a person can act on. Never shows a stack trace or a code. */
export function describeError(error: unknown): string {
  if (error instanceof NetworkError) {
    return error.timedOut
      ? "The server took too long to answer. Please try again."
      : "Cannot reach the server. Check your connection and try again.";
  }
  if (error instanceof ApiError) {
    switch (error.code) {
      case "not_authenticated":
        return "Incorrect email or password.";
      case "rate_limited":
        return "Too many attempts. Please wait a minute and try again.";
      case "file_too_large":
        return "That file is too large.";
      case "unsupported_file_type":
        return "That type of file is not accepted.";
      case "storage_quota_exceeded":
        return "You have used all of your storage.";
      case "validation_error":
        return "Please check the highlighted fields.";
    }
    if (error.status >= 500) return "Something went wrong on our side. Try again soon.";
    return error.message;
  }
  return "Something unexpected happened.";
}
