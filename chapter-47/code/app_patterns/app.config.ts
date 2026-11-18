import type { ConfigContext, ExpoConfig } from "expo/config";

// Replace the identifiers below with your own. They cannot be changed after a store release.
export default ({ config }: ConfigContext): ExpoConfig => ({
  ...config,
  name: "AI Chat",
  slug: "ai-chat",
  scheme: "aichat", // lets a link such as aichat://chat/42 open the app
  version: "1.0.0",
  orientation: "portrait",
  ios: {
    bundleIdentifier: "com.example.aichat",
    supportsTablet: false,
  },
  android: {
    package: "com.example.aichat",
    // The template adds these by default. We do not use them, so we remove them: fewer permissions
    // means a shorter store listing, an easier review, and less to explain to users.
    blockedPermissions: [
      "android.permission.SYSTEM_ALERT_WINDOW",
      "android.permission.READ_EXTERNAL_STORAGE",
      "android.permission.WRITE_EXTERNAL_STORAGE",
    ],
  },
  plugins: [
    "expo-router",
    "expo-secure-store",
    // The text the system shows when it asks for permission. Say what you use it for, and be honest.
    [
      "expo-camera",
      {
        cameraPermission: "AI Chat uses the camera only to scan codes. Nothing is saved or uploaded.",
        // We never record video with sound, so do not ask for the microphone at all. The plugin
        // adds RECORD_AUDIO on Android by default, and a permission you do not need is a
        // permission a reviewer, and a user, will question.
        recordAudioAndroid: false,
        microphonePermission: false,
      },
    ],
    "expo-notifications",
  ],
  extra: {
    // Filled in by `eas init`. Push tokens need it. It identifies the project and is not secret.
    eas: { projectId: process.env.EAS_PROJECT_ID },
  },
});
