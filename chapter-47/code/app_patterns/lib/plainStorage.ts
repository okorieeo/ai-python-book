import AsyncStorage from "@react-native-async-storage/async-storage";

import type { KeyValueStore } from "@/lib/core";

/** For things that are not secret: the offline queue, cached lists, settings. */
export const plainStorage: KeyValueStore = {
  getItem: (key) => AsyncStorage.getItem(key),
  setItem: (key, value) => AsyncStorage.setItem(key, value),
  removeItem: (key) => AsyncStorage.removeItem(key),
};
