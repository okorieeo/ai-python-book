/** The error format designed in Chapter 8, for our own route handlers. */
export function apiError(
  status: number,
  code: string,
  message: string,
  details?: Record<string, string[]>,
) {
  const requestId = "req_" + crypto.randomUUID().slice(0, 6);
  return Response.json(
    {
      error: {
        code,
        message,
        request_id: requestId,
        ...(details && { details }),
      },
    },
    { status },
  );
}
