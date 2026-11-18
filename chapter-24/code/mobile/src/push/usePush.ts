import * as Notifications from "expo-notifications";
import { router } from "expo-router";
import { useEffect } from "react";

import { enablePush } from "./pushActions";
import { routeFromNotificationData } from "./pushRules";

/** Keeps the server's copy of our token fresh. Mount once, while signed in. */
export function usePushSync() {
  useEffect(() => {
    // Silent: if the person already allowed notifications, re-register. Never ask here.
    enablePush(false).catch(() => {});
    // The system can replace the device token at any time. The old one then stops working.
    const sub = Notifications.addPushTokenListener(() => {
      enablePush(false).catch(() => {});
    });
    return () => sub.remove();
  }, []);
}

/** Opens the right screen when the person taps a notification (also from a cold start). */
export function useNotificationObserver() {
  useEffect(() => {
    function open(notification: Notifications.Notification) {
      const route = routeFromNotificationData(notification.request.content.data);
      if (route) router.push(route as never);
      Notifications.clearLastNotificationResponse();
    }
    const last = Notifications.getLastNotificationResponse();
    if (last?.notification) open(last.notification);
    const sub = Notifications.addNotificationResponseReceivedListener((r) => open(r.notification));
    return () => sub.remove();
  }, []);
}
