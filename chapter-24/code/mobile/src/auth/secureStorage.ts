import * as SecureStore from "expo-secure-store";

import type { KeyValueStorage } from "./tokenStore";

// WHEN_UNLOCKED_THIS_DEVICE_ONLY: readable only while the phone is unlocked, and
// never copied to another device through a backup. (iOS option; Android ignores it.)
const options = { keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY };

export const secureStorage: KeyValueStorage = {
  async getItem(key) {
    try {
      return await SecureStore.getItemAsync(key, options);
    } catch {
      return null; // a broken keystore means "not signed in", not a crash
    }
  },
  setItem: (key, value) => SecureStore.setItemAsync(key, value, options),
  removeItem: (key) => SecureStore.deleteItemAsync(key, options),
};
