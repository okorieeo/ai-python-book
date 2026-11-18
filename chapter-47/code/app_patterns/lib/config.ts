import { loadConfig } from "@/lib/core";

// Expo copies EXPO_PUBLIC_ variables into the app when you write them out in full, like this.
// A lookup such as process.env[name] is not replaced. And the values are readable by anyone
// who installs the app, so they are for addresses, never secrets.
export const config = loadConfig(
  {
    EXPO_PUBLIC_API_URL: process.env.EXPO_PUBLIC_API_URL,
    EXPO_PUBLIC_WS_URL: process.env.EXPO_PUBLIC_WS_URL,
  },
  __DEV__ ? "development" : "production",
);
