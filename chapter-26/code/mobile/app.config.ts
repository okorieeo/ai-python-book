import type { ConfigContext, ExpoConfig } from "expo/config";

import { resolveVariant } from "./config/variants";

// Created by `eas init`. Replace both values.
const EAS_PROJECT_ID = "00000000-0000-0000-0000-000000000000";
const EXPO_OWNER = "your-expo-username";

export default ({ config }: ConfigContext): ExpoConfig => {
  const variant = resolveVariant(process.env.APP_VARIANT);

  return {
    ...config,
    name: variant.appName,
    slug: "ai-chat-app",
    owner: EXPO_OWNER,
    // The version people see in the store. You change this by hand, on purpose.
    // The build number / version code is NOT here: Expo Build manages it
    // remotely (cli.appVersionSource = "remote" in eas.json).
    version: "1.0.0",
    orientation: "portrait",
    icon: "./assets/icon.png",
    scheme: variant.scheme,
    userInterfaceStyle: "automatic",

    // An update may only reach builds with the same native code. "appVersion"
    // ties the runtime version to `version` above (see 26.9).
    runtimeVersion: { policy: "appVersion" },
    updates: { url: `https://u.expo.dev/${EAS_PROJECT_ID}` },

    ios: {
      bundleIdentifier: variant.bundleId,
      supportsTablet: true,
      infoPlist: {
        // We only use the encryption built into iOS (HTTPS). See 26.7.
        ITSAppUsesNonExemptEncryption: false,
        // Adjust these two to match the permissions you added in Chapter 24.
        NSCameraUsageDescription:
          "AI Chat uses the camera so you can attach a photo to a message.",
        NSPhotoLibraryUsageDescription:
          "AI Chat reads photos you choose so you can attach them to a message.",
      },
    },
    android: {
      package: variant.bundleId,
      adaptiveIcon: {
        foregroundImage: "./assets/adaptive-icon.png",
        backgroundColor: "#1E3A8A",
      },
    },
    plugins: ["expo-router", "expo-secure-store"],
    extra: {
      variant: variant.name,
      eas: { projectId: EAS_PROJECT_ID },
    },
  };
};
