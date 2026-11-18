import { useNetInfo } from '@react-native-community/netinfo';
import { connectionQuality, isOnline, shouldDeferLargeTransfers } from '../lib/net/connectivity';

export function useConnectivity() {
  const state = useNetInfo();
  return {
    online: isOnline(state),
    quality: connectionQuality(state),
    deferLargeTransfers: shouldDeferLargeTransfers(state),
  };
}
