import Constants from "expo-constants";
import { Platform } from "react-native";

// EXPO_PUBLIC_* values are copied INTO the app when it is built. They are not secret:
// anyone can unpack the app and read them. Never put a key or a password here.
//
// A phone cannot reach "localhost" on your laptop. The Android emulator calls your
// laptop 10.0.2.2; a real phone needs your laptop address on the Wi-Fi (e.g. 192.168.1.20).
const fallback = Platform.OS === "android" ? "http://10.0.2.2:8000" : "http://localhost:8000";

export const API_URL = process.env.EXPO_PUBLIC_API_URL || fallback;
export const API_BASE = `${API_URL}/api/v1`;
export const WS_URL = process.env.EXPO_PUBLIC_WS_URL || API_URL.replace(/^http/, "ws");

// Written into app.json by `eas init`. Push tokens are issued for this project.
export const EAS_PROJECT_ID: string | undefined =
  Constants.expoConfig?.extra?.eas?.projectId ?? Constants.easConfig?.projectId;
