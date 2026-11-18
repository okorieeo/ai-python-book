import * as Application from "expo-application";
import Constants from "expo-constants";
import * as Updates from "expo-updates";

/** Everything support needs to know about THIS install. Show it on the About screen. */
export function getReleaseInfo() {
  return {
    variant: (Constants.expoConfig?.extra as { variant?: string } | undefined)?.variant ?? "unknown",
    version: Application.nativeApplicationVersion ?? "unknown",
    build: Application.nativeBuildVersion ?? "unknown", // build number (iOS) / version code (Android)
    runtimeVersion: Updates.runtimeVersion ?? "none",
    channel: Updates.channel ?? "none",
    updateId: Updates.updateId ?? "embedded", // "embedded" = no update applied yet
    isEmbeddedLaunch: Updates.isEmbeddedLaunch,
  };
}
