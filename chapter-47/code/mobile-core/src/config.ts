export interface AppConfig {
  apiUrl: string;
  wsUrl: string;
}

/**
 * Read settings from environment variables. In Expo, variables that start with EXPO_PUBLIC_ are
 * copied into the app bundle as plain text, so anyone can read them. They are for addresses and
 * public identifiers. Never put a secret in one.
 */
export function loadConfig(
  env: Record<string, string | undefined>,
  mode: "development" | "production",
): AppConfig {
  const apiUrl = (env.EXPO_PUBLIC_API_URL ?? "").trim().replace(/\/+$/, "");
  const wsUrl = (env.EXPO_PUBLIC_WS_URL ?? "").trim().replace(/\/+$/, "");
  if (!apiUrl) throw new Error("EXPO_PUBLIC_API_URL is not set");
  if (!wsUrl) throw new Error("EXPO_PUBLIC_WS_URL is not set");
  if (!/^https?:\/\//.test(apiUrl)) throw new Error("EXPO_PUBLIC_API_URL must start with http:// or https://");
  if (!/^wss?:\/\//.test(wsUrl)) throw new Error("EXPO_PUBLIC_WS_URL must start with ws:// or wss://");
  if (mode === "production") {
    if (!apiUrl.startsWith("https://")) throw new Error("Production must use https:// for the API");
    if (!wsUrl.startsWith("wss://")) throw new Error("Production must use wss:// for WebSockets");
  }
  return { apiUrl, wsUrl };
}
