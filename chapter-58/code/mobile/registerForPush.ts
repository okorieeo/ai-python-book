import Constants from "expo-constants";
import * as Device from "expo-device";
import * as Notifications from "expo-notifications";
import { Platform } from "react-native";

const API = process.env.EXPO_PUBLIC_API_URL!;

// Show alerts while the app is open too, not only when it is in the background.
Notifications.setNotificationHandler({
  handleNotification: async () => ({ shouldShowBanner: true, shouldShowList: true, shouldPlaySound: true, shouldSetBadge: false }),
});

/** Asks permission and registers this phone's Expo push token with our API. Call it after login.
 *  Returns the token, or null if push cannot work here (simulator, permission refused). NOT run in the book's test environment. */
export async function registerForPush(authHeaders: Record<string, string>): Promise<string | null> {
  if (!Device.isDevice) return null;                                     // simulators cannot receive push notifications

  if (Platform.OS === "android") {
    // Android 8+ needs a channel, and Android 13+ asks for permission only AFTER a channel exists
    await Notifications.setNotificationChannelAsync("alerts", {
      name: "Farm alerts", importance: Notifications.AndroidImportance.MAX, vibrationPattern: [0, 250, 250, 250],
    });
  }

  let { status } = await Notifications.getPermissionsAsync();
  if (status !== "granted") status = (await Notifications.requestPermissionsAsync()).status;
  if (status !== "granted") return null;

  const projectId = Constants.expoConfig?.extra?.eas?.projectId ?? Constants.easConfig?.projectId;
  if (!projectId) throw new Error("Missing EAS project id: run `eas init` (needed for push tokens).");
  const { data: token } = await Notifications.getExpoPushTokenAsync({ projectId });

  await fetch(`${API}/api/push-tokens/`, {
    method: "POST", headers: { "Content-Type": "application/json", ...authHeaders },
    body: JSON.stringify({ token, platform: Platform.OS }),
  });
  return token;
}
