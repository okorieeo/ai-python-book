/** The error format from Chapter 8: { error: { code, message, details? }, request_id } */
export type ErrorDetails = Record<string, string[]>;

export class ApiError extends Error {
  status: number;
  code: string;
  details: ErrorDetails;
  requestId: string | null;
  retryAfter: number | null;

  constructor(init: {
    status: number;
    code: string;
    message: string;
    details?: ErrorDetails;
    requestId?: string | null;
    retryAfter?: number | null;
  }) {
    super(init.message);
    this.name = "ApiError";
    this.status = init.status;
    this.code = init.code;
    this.details = init.details ?? {};
    this.requestId = init.requestId ?? null;
    this.retryAfter = init.retryAfter ?? null;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** Build an ApiError from a failed Response. Never throws: bad bodies become generic errors. */
export async function errorFromResponse(response: Response): Promise<ApiError> {
  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }
  const error = isRecord(body) && isRecord(body.error) ? body.error : {};
  const retryAfter = Number(response.headers.get("retry-after"));
  return new ApiError({
    status: response.status,
    code: typeof error.code === "string" ? error.code : defaultCode(response.status),
    message: typeof error.message === "string" ? error.message : "The request failed.",
    details: normalizeDetails(error.details),
    requestId:
      (isRecord(body) && typeof body.request_id === "string" ? body.request_id : null) ??
      response.headers.get("x-request-id"),
    retryAfter: Number.isFinite(retryAfter) && retryAfter > 0 ? retryAfter : null,
  });
}

function normalizeDetails(details: unknown): ErrorDetails {
  if (!isRecord(details)) return {};
  const result: ErrorDetails = {};
  for (const [field, value] of Object.entries(details)) {
    if (Array.isArray(value)) result[field] = value.map(String);
    else if (typeof value === "string") result[field] = [value];
  }
  return result;
}

function defaultCode(status: number): string {
  if (status === 401) return "not_authenticated";
  if (status === 403) return "permission_denied";
  if (status === 404) return "not_found";
  if (status === 429) return "rate_limited";
  if (status >= 500) return "internal_error";
  return "error";
}

/** Friendly text for each stable error code. The UI uses these instead of raw server messages. */
const MESSAGES: Record<string, string> = {
  network_error: "We couldn\u2019t reach the server. Check your connection and try again.",
  timeout: "The request took too long. Please try again.",
  not_authenticated: "Please log in to continue.",
  session_expired: "Your session has expired. Please log in again.",
  authentication_failed: "Incorrect email or password.",
  permission_denied: "You don\u2019t have permission to do that.",
  not_found: "We couldn\u2019t find what you were looking for.",
  rate_limited: "You\u2019re doing that too quickly. Please wait a moment.",
  quota_exceeded: "You\u2019ve used all your tokens for this month.",
  upstream_unavailable: "The service is temporarily unavailable. Please try again shortly.",
  internal_error: "Something went wrong on our side. Please try again.",
  csrf_blocked: "That request was blocked for your safety. Reload the page and try again.",
};

export function messageForError(error: unknown): string {
  if (error instanceof ApiError) {
    return MESSAGES[error.code] ?? (error.status >= 500 ? MESSAGES.internal_error : error.message);
  }
  return MESSAGES.internal_error;
}

/** Should a failed request be retried automatically? Only transient problems: never 4xx. */
export function isRetryable(error: unknown): boolean {
  if (!(error instanceof ApiError)) return false;
  return error.code === "network_error" || error.code === "timeout" || [502, 503, 504].includes(error.status);
}
