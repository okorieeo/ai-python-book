import type { OfflineQueue } from "./offlineQueue";
import type { SocketManager } from "./socket";

/** What the app needs to know about connectivity. Back it with @react-native-community/netinfo. */
export interface NetworkMonitor {
  isOnline(): boolean;
  subscribe(listener: (online: boolean) => void): () => void;
}

/** For tests and previews: you decide when the phone goes on and offline. */
export class ManualNetwork implements NetworkMonitor {
  private online: boolean;
  private readonly listeners = new Set<(online: boolean) => void>();
  constructor(online = true) {
    this.online = online;
  }
  isOnline(): boolean {
    return this.online;
  }
  set(online: boolean): void {
    this.online = online;
    for (const l of this.listeners) l(online);
  }
  subscribe(listener: (online: boolean) => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }
}

/**
 * Coming back online is the moment to send what is waiting and to reconnect the socket.
 * (NetInfo reports `isConnected` and `isInternetReachable`. Treat "online" as connected AND
 * reachable not equal to false, because reachable can be null while it is still checking.)
 */
export function wireConnectivity(monitor: NetworkMonitor, parts: { queue?: OfflineQueue; socket?: SocketManager }): () => void {
  return monitor.subscribe((online) => {
    parts.socket?.setOnline(online);
    if (online) void parts.queue?.flush();
  });
}
