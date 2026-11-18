import Constants from "expo-constants";
import * as Device from "expo-device";
import * as Notifications from "expo-notifications";
import { useRouter } from "expo-router";
import { useEffect } from "react";
import { Platform } from "react-native";

import { routeForNotification } from "@/lib/core";

import { api } from "./api";

// Since SDK 58 a notification that arrives while the app is open is shown unless you say otherwise.
// Decide deliberately: here, a quiet banner and an entry in the list, no sound.
Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowBanner: true,
    shouldShowList: true,
    shouldPlaySound: false,
    shouldSetBadge: false,
  }),
});

/** Ask for permission, get this device's push token, and tell the backend about it. */
export async function registerForPush(): Promise<string | null> {
  if (!Device.isDevice) return null; // simulators cannot receive push notifications

  if (Platform.OS === "android") {
    // Android 8 and later require a channel, and the user can tune each channel in Settings.
    await Notifications.setNotificationChannelAsync("default", {
      name: "Messages",
      importance: Notifications.AndroidImportance.DEFAULT,
    });
  }

  const existing = await Notifications.getPermissionsAsync();
  let granted = existing.granted;
  if (!granted && existing.canAskAgain) {
    granted = (await Notifications.requestPermissionsAsync()).granted; // ask in context, not at launch
  }
  if (!granted) return null;

  const projectId = Constants.expoConfig?.extra?.eas?.projectId ?? Constants.easConfig?.projectId;
  if (!projectId) throw new Error("No EAS project id: run `eas init` so push tokens can be created");
  const { data: token } = await Notifications.getExpoPushTokenAsync({ projectId });

  await api.post("/api/v1/devices/", { token, platform: Platform.OS }, { idempotencyKey: `device:${token}` });
  return token;
}

/** Open the right screen when the user taps a notification. The payload is untrusted input. */
export function useNotificationRouting() {
  const router = useRouter();
  useEffect(() => {
    const subscription = Notifications.addNotificationResponseReceivedListener((response) => {
      const route = routeForNotification(response.notification.request.content.data);
      if (route) router.push(route as never);
    });
    return () => subscription.remove();
  }, [router]);
}
