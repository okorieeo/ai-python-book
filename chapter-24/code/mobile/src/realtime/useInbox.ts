import { useEffect, useRef, useState } from "react";
import { AppState } from "react-native";

import { api } from "../api";
import { WS_URL } from "../config";
import { createSocket, type SocketStatus } from "./socket";

export interface InboxItem {
  id: string;
  title: string;
  body: string;
  created_at: string;
}

const isItem = (m: any): m is InboxItem & { type: "notification" } =>
  m && m.type === "notification" && typeof m.id === "string" && typeof m.title === "string";

export function useInbox() {
  const [items, setItems] = useState<InboxItem[]>([]);
  const [status, setStatus] = useState<SocketStatus>("idle");
  const socketRef = useRef<ReturnType<typeof createSocket> | null>(null);

  useEffect(() => {
    const socket = createSocket({
      // A fresh one-use ticket for every attempt (Chapter 14).
      getUrl: async () => {
        const { ticket } = await api.socketTicket();
        return `${WS_URL}/ws/notifications/?ticket=${encodeURIComponent(ticket)}`;
      },
      onStatus: setStatus,
      onMessage: (message) => {
        if (!isItem(message)) return;
        // keep the newest 50, and ignore a repeat of an id we already have
        setItems((old) =>
          old.some((i) => i.id === message.id) ? old : [message, ...old].slice(0, 50),
        );
      },
    });
    socketRef.current = socket;
    socket.start();

    // Phones kill sockets of sleeping apps. Close when hidden, reconnect when shown.
    const sub = AppState.addEventListener("change", (state) => {
      if (state === "active") {
        socket.start();
        socket.reconnectNow();
      } else {
        socket.stop();
      }
    });
    return () => {
      sub.remove();
      socket.stop();
    };
  }, []);

  return { items, status };
}
