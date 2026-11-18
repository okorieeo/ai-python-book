/**
 * Server-side configuration for calls from Next.js server code to the Django API.
 *
 * The first version of this code used `process.env.API_INTERNAL_URL ?? "http://localhost:8000"`.
 * That silent default was the ROOT CAUSE of the bug in section 49.8: inside a Docker container,
 * "localhost" is the container itself, so every request failed with ECONNREFUSED.
 * Now production refuses to guess.
 */
type Env = Record<string, string | undefined>;

export function apiInternalUrl(env: Env = process.env): string {
  const url = env.API_INTERNAL_URL;
  if (!url) {
    if (env.NODE_ENV === "production") {
      throw new Error(
        "API_INTERNAL_URL is not set. In Docker Compose use http://backend:8000 (the service name, not localhost).",
      );
    }
    return "http://localhost:8000"; // fine on a laptop where the API runs on the same machine
  }
  return url.replace(/\/+$/, "");
}
