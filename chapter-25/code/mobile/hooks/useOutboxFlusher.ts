import NetInfo from '@react-native-community/netinfo';
import { useEffect } from 'react';
import { AppState } from 'react-native';
import { isOnline } from '../lib/net/connectivity';
import { outbox } from '../lib/offline/outboxInstance';

/** Mount once, near the root. Tries to send the queue whenever it could newly succeed. */
export function useOutboxFlusher(): void {
  useEffect(() => {
    const flush = () => void outbox.flush();

    void outbox.load().then(flush); // app start: finish what the last session left behind
    const unsubscribeNet = NetInfo.addEventListener((state) => {
      if (isOnline(state)) flush(); // the network came back
    });
    const appState = AppState.addEventListener('change', (status) => {
      if (status === 'active') flush(); // the user came back
    });
    const timer = setInterval(flush, 30_000); // items whose backoff has expired; cheap when nothing is due

    return () => {
      unsubscribeNet();
      appState.remove();
      clearInterval(timer);
    };
  }, []);
}
