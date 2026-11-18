import { Stack } from "expo-router";
import * as SplashScreen from "expo-splash-screen";
import { useEffect } from "react";
import { Button, Text, View } from "react-native";

import { AuthProvider, useAuth } from "../src/auth/AuthContext";
import { installForegroundHandler } from "../src/push/pushActions";
import { useNotificationObserver } from "../src/push/usePush";

SplashScreen.preventAutoHideAsync(); // keep the splash up until we know who is signed in
installForegroundHandler();

function Gate() {
  const { state, retry } = useAuth();
  const signedIn = state.status === "signedIn";

  useEffect(() => {
    if (state.status !== "loading") void SplashScreen.hideAsync();
  }, [state.status]);

  if (state.status === "loading") return null;
  if (state.status === "offline") {
    return (
      <View style={{ flex: 1, alignItems: "center", justifyContent: "center", padding: 24 }}>
        <Text style={{ fontSize: 16, marginBottom: 12, textAlign: "center" }}>
          Cannot reach the server. Your session is safe.
        </Text>
        <Button title="Try again" onPress={retry} />
      </View>
    );
  }

  return (
    <Stack screenOptions={{ headerShown: false }}>
      {/* Routes inside a closed guard do not exist: a deep link cannot open them. */}
      <Stack.Protected guard={signedIn}>
        <Stack.Screen name="(tabs)" />
      </Stack.Protected>
      <Stack.Protected guard={!signedIn}>
        <Stack.Screen name="(auth)" />
      </Stack.Protected>
    </Stack>
  );
}

function SignedInEffects() {
  const { state } = useAuth();
  return state.status === "signedIn" ? <NotificationRouting /> : null;
}
function NotificationRouting() {
  useNotificationObserver();
  return null;
}

export default function RootLayout() {
  return (
    <AuthProvider>
      <Gate />
      <SignedInEffects />
    </AuthProvider>
  );
}
