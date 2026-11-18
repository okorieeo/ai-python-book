import createClient from "openapi-fetch";
import type { paths } from "./generated/schema";

/**
 * The one typed API client for the web app. `paths` is generated from contracts/openapi.json
 * (npm run api:types), so a wrong URL, method, parameter or body is a compile error.
 */
export const api = createClient<paths>({
  baseUrl: process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
  credentials: "include",
});

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

/** Turn openapi-fetch's { data, error } result into "return data or throw". */
export function unwrap<T>(result: { data?: T; error?: unknown; response: Response }): T {
  if (result.data === undefined) {
    const message =
      typeof result.error === "object" && result.error && "message" in result.error
        ? String((result.error as { message: unknown }).message)
        : `Request failed (${result.response.status})`;
    throw new ApiError(result.response.status, message);
  }
  return result.data;
}
