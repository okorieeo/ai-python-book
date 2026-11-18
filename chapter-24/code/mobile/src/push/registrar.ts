import { ApiError } from "../api/errors";
import type { Endpoints } from "../api/endpoints";
import type { KeyValueStorage } from "../auth/tokenStore";

export const DEVICE_KEY = "push.device_id";

/** Tells the server "send pushes for this account to this token", and takes it back. */
export function createDeviceRegistrar(deps: {
  storage: KeyValueStorage;
  api: Pick<Endpoints, "registerDevice" | "unregisterDevice">;
}) {
  const { storage, api } = deps;

  return {
    // Safe to call on every launch: the server treats it as an upsert.
    async register(token: string, platform: "ios" | "android", deviceName: string) {
      const device = await api.registerDevice(token, platform, deviceName);
      await storage.setItem(DEVICE_KEY, device.id);
      return device.id;
    },

    async isRegistered() {
      return (await storage.getItem(DEVICE_KEY)) !== null;
    },

    // Called on logout. A 404 means the server already forgot it: that is fine.
    async unregister() {
      const id = await storage.getItem(DEVICE_KEY);
      if (!id) return;
      try {
        await api.unregisterDevice(id);
      } catch (e) {
        if (!(e instanceof ApiError && e.status === 404)) throw e;
      }
      await storage.removeItem(DEVICE_KEY);
    },
  };
}

export type DeviceRegistrar = ReturnType<typeof createDeviceRegistrar>;
