import NetInfo from '@react-native-community/netinfo';
import { focusManager, onlineManager } from '@tanstack/react-query';
import { AppState } from 'react-native';
import { isOnline } from './connectivity';

/**
 * Call once at startup, before the first render. Makes NetInfo the single source of truth for
 * "are we online?" and the app's foreground state the source of truth for "is the user looking?".
 */
export function setupNetworkManagers(apiBaseUrl: string): void {
  NetInfo.configure({
    // Ask OUR server whether the internet works, not the phone's idea of it. Captive portals and
    // networks that block the system's own check then show up as offline when they really are.
    reachabilityUrl: `${apiBaseUrl}/health/`,
    reachabilityTest: async (response) => response.status === 200,
    reachabilityLongTimeout: 60_000, // while reachable: check once a minute
    reachabilityShortTimeout: 5_000, // while unreachable: check every 5 s
    reachabilityRequestTimeout: 10_000,
    useNativeReachability: false, // use the probe above on iOS and Android too
  });

  onlineManager.setEventListener((setOnline) => NetInfo.addEventListener((state) => setOnline(isOnline(state))));

  focusManager.setEventListener((handleFocus) => {
    const subscription = AppState.addEventListener('change', (status) => handleFocus(status === 'active'));
    return () => subscription.remove();
  });
}
