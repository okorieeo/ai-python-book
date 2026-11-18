import { readBffConfig, type BffConfig } from "./config";

let cached: BffConfig | null = null;

/** Server-side configuration, read once from the environment. Never import this from client components. */
export function bffConfig(): BffConfig {
  cached ??= readBffConfig(process.env);
  return cached;
}
