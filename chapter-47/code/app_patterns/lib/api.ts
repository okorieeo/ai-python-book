import { ApiClient, OfflineQueue, SocketManager, TokenStore, wireConnectivity } from "@/lib/core";
import type { NetworkMonitor } from "@/lib/core";
import NetInfo from "@react-native-community/netinfo";

import { config } from "./config";
import { plainStorage } from "./plainStorage";
import { secureStorage } from "./secureStorage";

type Listener = () => void;
const sessionListeners = new Set<Listener>();
export const onSessionExpired = (fn: Listener) => {
  sessionListeners.add(fn);
  return () => {
    sessionListeners.delete(fn); // a cleanup function must return nothing, so no `return` here
  };
};

export const tokenStore = new TokenStore(secureStorage);

export const api = new ApiClient({
  baseUrl: config.apiUrl,
  tokenStore,
  onSessionExpired: () => sessionListeners.forEach((fn) => fn()),
  onLog: (e) => {
    if (__DEV__) console.log(`${e.method} ${e.path} -> ${e.status} (${e.ms} ms) ${e.requestId}`);
  },
});

// NetInfo says "reachable" can be null while it is still checking: only an explicit false means offline.
let online = true;
const network: NetworkMonitor = {
  isOnline: () => online,
  subscribe: (listener) =>
    NetInfo.addEventListener((state) => {
      online = Boolean(state.isConnected) && state.isInternetReachable !== false;
      listener(online);
    }),
};

export const queue = new OfflineQueue({ storage: plainStorage, client: api, isOnline: network.isOnline });

export const socket = new SocketManager({
  url: `${config.wsUrl}/ws/chat/`,
  getToken: async () => (await tokenStore.get())?.access ?? null,
});

/** Call once at start-up. Returns a function that stops listening. */
export function startConnectivity(): () => void {
  void queue.load();
  return wireConnectivity(network, { queue, socket });
}
