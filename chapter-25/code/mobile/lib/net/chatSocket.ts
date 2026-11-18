import { onlineManager } from '@tanstack/react-query';
import { AppState } from 'react-native';
import { queryClient } from '../query/client';
import { ReconnectingSocket, ReconnectPolicy, type SocketStatus } from './reconnect';

/**
 * Adapt to the WebSocket client you wrote in Chapter 24 (URL, token, message format).
 * What matters here: reconnect rules live in ONE place, and REST stays the source of truth.
 */
export function createChatSocket(options: {
  /** Called for every (re)connect, so it can add a fresh short-lived ticket or token each time. */
  url: () => string;
  onEvent: (event: unknown) => void;
  onStatus?: (status: SocketStatus) => void;
}) {
  const socket = new ReconnectingSocket({
    createSocket: () => new WebSocket(options.url()),
    onMessage: (data) => {
      try {
        options.onEvent(JSON.parse(String(data)));
      } catch {
        // ignore a frame we cannot read; never let one bad frame close the screen
      }
    },
    onStatus: (status) => {
      options.onStatus?.(status);
      // Whatever we missed while disconnected is on the server: fetch it.
      if (status === 'open') void queryClient.invalidateQueries({ queryKey: ['messages'] });
    },
    policy: new ReconnectPolicy({ maxAttempts: 8, maxDelayMs: 30_000 }),
  });

  const stopOnline = onlineManager.subscribe((online) => socket.setOnline(online));
  const appState = AppState.addEventListener('change', (status) => {
    if (status === 'active' && socket.status === 'gave-up') socket.start(); // the user came back: try again
  });

  return {
    start: () => socket.start(),
    send: (data: string) => socket.send(data),
    stop: () => {
      stopOnline();
      appState.remove();
      socket.stop();
    },
  };
}
