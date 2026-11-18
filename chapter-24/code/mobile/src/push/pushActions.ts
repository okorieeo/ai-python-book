import * as Device from "expo-device";
import * as Notifications from "expo-notifications";
import { Platform } from "react-native";

import { deviceRegistrar } from "../api";
import { EAS_PROJECT_ID } from "../config";

export type PushResult =
  | { kind: "ok"; token: string }
  | { kind: "denied"; canAskAgain: boolean }
  | { kind: "unavailable"; reason: string };

// How a notification looks while the app is OPEN. Call once, at startup.
export function installForegroundHandler() {
  Notifications.setNotificationHandler({
    handleNotification: async () => ({
      shouldShowBanner: true,
      shouldShowList: true,
      shouldPlaySound: true, // on Android, false would hide the banner as well
      shouldSetBadge: false,
    }),
  });
}

const allowed = (p: Notifications.NotificationPermissionsStatus) =>
  p.granted || p.ios?.status === Notifications.IosAuthorizationStatus.PROVISIONAL;

/**
 * askUser=false  look only (used silently at launch)
 * askUser=true   show the system dialog if the system still allows it
 */
export async function getPushToken(askUser: boolean): Promise<PushResult> {
  // Android 13+ shows its permission dialog only once a channel exists, so this comes first.
  if (Platform.OS === "android") {
    await Notifications.setNotificationChannelAsync("default", {
      name: "General",
      importance: Notifications.AndroidImportance.HIGH,
    });
  }

  let permission = await Notifications.getPermissionsAsync();
  if (!allowed(permission) && permission.canAskAgain && askUser) {
    permission = await Notifications.requestPermissionsAsync();
  }
  if (!allowed(permission)) return { kind: "denied", canAskAgain: permission.canAskAgain };

  if (!EAS_PROJECT_ID) {
    return { kind: "unavailable", reason: "No EAS project id. Run `eas init` and rebuild." };
  }
  try {
    const token = await Notifications.getExpoPushTokenAsync({ projectId: EAS_PROJECT_ID });
    return { kind: "ok", token: token.data };
  } catch (e) {
    // Offline, no Google Play services, missing credentials: report it, do not crash.
    return { kind: "unavailable", reason: e instanceof Error ? e.message : String(e) };
  }
}

/** Get a token (asking if allowed) and tell the server about it. */
export async function enablePush(askUser: boolean): Promise<PushResult> {
  const result = await getPushToken(askUser);
  if (result.kind === "ok") {
    const platform = Platform.OS === "ios" ? "ios" : "android";
    await deviceRegistrar.register(result.token, platform, Device.modelName ?? Platform.OS);
  }
  return result;
}

export async function disablePush() {
  await deviceRegistrar.unregister();
}
