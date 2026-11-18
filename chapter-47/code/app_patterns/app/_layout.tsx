import { Stack } from "expo-router";
import { useEffect } from "react";

import { startConnectivity } from "@/lib/api";
import { AuthProvider, useAuth } from "@/lib/auth";
import { useNotificationRouting } from "@/lib/notifications";

function Routes() {
  const { status } = useAuth();
  useNotificationRouting();
  if (status === "loading") return null; // keep the splash screen up while we read the Keychain
  return (
    <Stack screenOptions={{ headerShown: false }}>
      {/* Signed-in screens cannot be reached by a deep link until the user has signed in. */}
      <Stack.Protected guard={status === "signedIn"}>
        <Stack.Screen name="index" />
        <Stack.Screen name="chat/[id]" options={{ headerShown: true, title: "Chat" }} />
        <Stack.Screen name="scan" options={{ headerShown: true, title: "Scan" }} />
      </Stack.Protected>
      <Stack.Protected guard={status === "signedOut"}>
        <Stack.Screen name="sign-in" />
      </Stack.Protected>
    </Stack>
  );
}

export default function RootLayout() {
  useEffect(() => startConnectivity(), []);
  return (
    <AuthProvider>
      <Routes />
    </AuthProvider>
  );
}
