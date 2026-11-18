import * as SecureStore from "expo-secure-store";

import type { KeyValueStore } from "@/lib/core";

/**
 * Tokens go in the Keychain (iOS) or the Keystore-backed store (Android), never in AsyncStorage.
 * AFTER_FIRST_UNLOCK_THIS_DEVICE_ONLY lets a background refresh work once the phone has been
 * unlocked since boot, and keeps the value out of device backups and transfers.
 * SecureStore keys may contain only letters, digits, ".", "-" and "_".
 */
export const secureStorage: KeyValueStore = {
  getItem: (key) => SecureStore.getItemAsync(key),
  setItem: (key, value) =>
    SecureStore.setItemAsync(key, value, {
      keychainAccessible: SecureStore.AFTER_FIRST_UNLOCK_THIS_DEVICE_ONLY,
    }),
  removeItem: (key) => SecureStore.deleteItemAsync(key),
};
