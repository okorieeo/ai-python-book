export type BffConfig = {
  backendUrl: string; // server-side only, e.g. http://localhost:8000 (in Docker: http://backend:8000)
  secureCookies: boolean;
  appOrigin?: string; // the public origin of this web app, for the CSRF check; derived from the request when omitted
  accessSkewSeconds?: number;
  timeoutMs?: number;
  now?: () => number; // injectable clock (milliseconds) for tests
};

export function readBffConfig(env: Record<string, string | undefined>): BffConfig {
  const backendUrl = env.BACKEND_URL;
  if (!backendUrl) throw new Error("BACKEND_URL is not set (server-side environment variable, no NEXT_PUBLIC_ prefix)");
  return {
    backendUrl: backendUrl.replace(/\/+$/, ""),
    secureCookies: env.NODE_ENV === "production",
    appOrigin: env.APP_ORIGIN || undefined,
  };
}
