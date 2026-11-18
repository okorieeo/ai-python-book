export type FieldErrors = Record<string, string[]>;

export class ApiError extends Error {
  readonly status: number; // 0 means "the request never got an answer"
  readonly code: string;
  readonly requestId?: string;
  readonly fields: FieldErrors;
  readonly retryAfter?: number; // seconds, from the Retry-After header

  constructor(init: {
    status: number;
    code: string;
    message: string;
    requestId?: string;
    fields?: FieldErrors;
    retryAfter?: number;
  }) {
    super(init.message);
    this.name = "ApiError";
    this.status = init.status;
    this.code = init.code;
    this.requestId = init.requestId;
    this.fields = init.fields ?? {};
    this.retryAfter = init.retryAfter;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function parseFields(value: unknown): FieldErrors {
  if (!isRecord(value)) return {};
  const out: FieldErrors = {};
  for (const [key, messages] of Object.entries(value)) {
    if (Array.isArray(messages)) {
      out[key] = messages.filter((m): m is string => typeof m === "string");
    }
  }
  return out;
}

// Only this file knows the shape of the Chapter 8 error envelope:
// { "error": { "code", "message", "request_id", "fields" } }
// If your envelope differs, change this function and nothing else.
export function toApiError(status: number, body: unknown, headers: Headers): ApiError {
  const retryHeader = Number(headers.get("Retry-After"));
  const retryAfter = Number.isFinite(retryHeader) && retryHeader > 0 ? retryHeader : undefined;
  const envelope = isRecord(body) && isRecord(body.error) ? body.error : undefined;

  return new ApiError({
    status,
    code: typeof envelope?.code === "string" ? envelope.code : `http_${status}`,
    message: typeof envelope?.message === "string" ? envelope.message : "Request failed",
    requestId: typeof envelope?.request_id === "string" ? envelope.request_id : undefined,
    fields: parseFields(envelope?.fields),
    retryAfter,
  });
}

export function networkError(): ApiError {
  return new ApiError({
    status: 0,
    code: "network_error",
    message: "Could not reach the server",
  });
}

// What a person sees. Never show server text, stack traces or SQL (17.11):
// a generic sentence plus the request id is enough for a support request.
export function friendlyMessage(error: unknown): string {
  if (!(error instanceof ApiError)) return "Something went wrong. Please try again.";
  switch (true) {
    case error.status === 0:
      return "We could not reach the server. Check your connection and try again.";
    case error.status === 401:
      return "Your session has ended. Please sign in again.";
    case error.status === 429:
      return error.retryAfter
        ? `Too many attempts. Please try again in ${error.retryAfter} seconds.`
        : "Too many attempts. Please wait a moment and try again.";
    case error.status >= 500:
      return error.requestId
        ? `Something went wrong on our side. Quote this reference if you contact support: ${error.requestId}.`
        : "Something went wrong on our side. Please try again.";
    default:
      return error.message;
  }
}
