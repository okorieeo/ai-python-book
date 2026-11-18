/**
 * The few fields of NetInfo's state that we use. NetInfo's own NetInfoState type is assignable
 * to this, so the pure functions below can be tested without React Native.
 */
export interface NetState {
  isConnected: boolean | null;
  isInternetReachable: boolean | null;
  type?: string;
  details?: { isConnectionExpensive?: boolean; cellularGeneration?: string | null } | null;
}

/**
 * "Offline" only when we KNOW we are offline. At startup NetInfo reports null ("unknown") for a
 * moment; treating that as offline would flash a banner and block requests for no reason.
 * isConnected = a network interface is up. isInternetReachable = a probe got through.
 * A captive-portal Wi-Fi is connected but not reachable.
 */
export function isOnline(state: NetState): boolean {
  return state.isConnected !== false && state.isInternetReachable !== false;
}

export type ConnectionQuality = 'offline' | 'poor' | 'good' | 'unknown';

export function connectionQuality(state: NetState): ConnectionQuality {
  if (!isOnline(state)) return 'offline';
  if (state.isConnected === null) return 'unknown';
  if (state.type === 'cellular') {
    const generation = state.details?.cellularGeneration;
    if (generation === '2g' || generation === '3g') return 'poor';
  }
  return 'good';
}

/** Should the app hold back big downloads, uploads and image-heavy screens? */
export function shouldDeferLargeTransfers(state: NetState): boolean {
  const quality = connectionQuality(state);
  return quality === 'offline' || quality === 'poor' || state.details?.isConnectionExpensive === true;
}
