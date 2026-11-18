// One hook for web AND React Native: both have a global WebSocket and React.
import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import { chatReducer, initialChatState, type ClientMessage, type ServerEvent } from "./assistant-protocol.ts";

/** `url` already carries whatever sign-in your socket needs (Chapters 14 and 21). Reconnection follows Chapter 21. */
export function useAssistant(url: string) {
  const [state, dispatch] = useReducer(chatReducer, initialChatState);
  const [connected, setConnected] = useState(false);
  const socket = useRef<WebSocket | null>(null);

  useEffect(() => {
    let closed = false;
    let attempt = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const open = () => {
      const ws = new WebSocket(url);
      socket.current = ws;
      ws.onopen = () => {
        attempt = 0;
        setConnected(true);
      };
      ws.onmessage = (message) => {
        try {
          dispatch({ kind: "server", event: JSON.parse(String(message.data)) as ServerEvent });
        } catch {
          /* ignore anything that is not JSON */
        }
      };
      ws.onclose = () => {
        setConnected(false);
        if (!closed) timer = setTimeout(open, Math.min(1000 * 2 ** attempt++, 15_000)); // back off: 1s, 2s, 4s ... 15s
      };
    };

    open();
    return () => {
      closed = true;
      if (timer) clearTimeout(timer);
      socket.current?.close();
    };
  }, [url]);

  const send = useCallback((message: ClientMessage): boolean => {
    const ws = socket.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return false;
    ws.send(JSON.stringify(message));
    return true;
  }, []);

  const sendMessage = useCallback(
    (text: string) => {
      if (send({ type: "message", text })) dispatch({ kind: "user_sent", text });
    },
    [send],
  );

  const decide = useCallback(
    (actionId: string, approve: boolean) => {
      if (send({ type: "decision", action_id: actionId, approve })) dispatch({ kind: "decision_sent", actionId });
    },
    [send],
  );

  return { state, connected, sendMessage, decide, reset: () => dispatch({ kind: "reset" }) };
}
