import { isOlderThan, parseVersion } from "./version";

/** What GET /api/v1/app-config/?platform=ios returns (see backend/core/app_config). */
export interface AppConfigResponse {
  min_version: string;
  recommended_version: string;
  store_url: string;
  maintenance: boolean;
  message: string;
}

export type GateState =
  | { kind: "ok" }
  | { kind: "recommended"; storeUrl: string; message: string }
  | { kind: "blocked"; reason: "outdated" | "maintenance"; storeUrl: string; message: string };

const OK: GateState = { kind: "ok" };

/**
 * Decide what the app should do, given the server's policy and the installed version.
 *
 * Fail OPEN: if we have no policy, or the policy is malformed, let the person in.
 * That is the opposite of the security checks in Chapter 17 on purpose. A security
 * check that cannot run must refuse (fail closed); a version check that cannot run
 * must not lock every user out of the app because OUR server had a bad minute.
 */
export function evaluateGate(
  config: AppConfigResponse | null | undefined,
  installedVersion: string,
): GateState {
  if (!config) return OK;

  try {
    // Validate everything we will use before deciding anything.
    parseVersion(installedVersion);
    parseVersion(config.min_version);
    parseVersion(config.recommended_version);

    if (config.maintenance) {
      return {
        kind: "blocked",
        reason: "maintenance",
        storeUrl: config.store_url,
        message: config.message || "We are doing some maintenance. Please try again soon.",
      };
    }
    if (isOlderThan(installedVersion, config.min_version)) {
      return {
        kind: "blocked",
        reason: "outdated",
        storeUrl: config.store_url,
        message: config.message || "Please update the app to keep using it.",
      };
    }
    if (isOlderThan(installedVersion, config.recommended_version)) {
      return {
        kind: "recommended",
        storeUrl: config.store_url,
        message: config.message || "A new version is available.",
      };
    }
    return OK;
  } catch {
    return OK; // malformed policy or version: do not lock people out
  }
}
