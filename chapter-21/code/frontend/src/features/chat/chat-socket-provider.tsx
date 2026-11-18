"use client";

import { useQueryClient } from "@tanstack/react-query";
import {
  createContext, useCallback, useContext, useEffect, useMemo, useRef, useState,
  type ReactNode,
} from "react";
import { encodeCommand, parseServerEvent, type ClientCommand } from "@/lib/realtime/protocol";
import { ReconnectingSocket, type ConnectionStatus } from "@/lib/realtime/socket";
import { fetchWsTicket } from "./api";
import { findStaleSending } from "./chat-state";
import { useChatStore } from "./chat-store";
import { createDeltaBatcher } from "./delta-batcher";

const ACK_TIMEOUT_MS = 15_000;

interface ChatSocketValue {
  status: ConnectionStatus;
  send: (command: ClientCommand) => boolean;
  reconnectNow: () => void;
}

const ChatSocketContext = createContext<ChatSocketValue | null>(null);

export function ChatSocketProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const dispatch = useChatStore((s) => s.dispatch);
  const [status, setStatus] = useState<ConnectionStatus>("idle");
  const socketRef = useRef<ReconnectingSocket | null>(null);

  useEffect(() => {
    const url = process.env.NEXT_PUBLIC_WS_URL;
    if (!url) throw new Error("NEXT_PUBLIC_WS_URL is not set. See .env.local.example.");

    const batcher = createDeltaBatcher((message_id, delta) =>
      dispatch({ type: "server", event: { type: "assistant.delta", message_id, delta } }),
    );
    let previous: ConnectionStatus = "idle";
    let hasOpened = false;

    const socket = new ReconnectingSocket({
      url,
      getTicket: fetchWsTicket,
      onMessage: (raw) => {
        const event = parseServerEvent(raw);
        if (!event) return; // unknown or malformed: ignore it, never crash on server data
        if (event.type === "assistant.delta") {
          batcher.push(event.message_id, event.delta);
          return;
        }
        batcher.flush(); // text that arrived before this event must be applied first
        dispatch({ type: "server", event });
      },
      onStatus: (next) => {
        setStatus(next);
        if (next === "open") {
          // After a reconnect, history on the server is the truth: fetch it to fill any gap.
          if (hasOpened) void queryClient.invalidateQueries({ queryKey: ["messages"] });
          hasOpened = true;
        } else if (previous === "open") {
          batcher.flush();
          dispatch({ type: "connection/lost" });
        }
        previous = next;
      },
    });
    socketRef.current = socket;
    socket.connect();

    const wake = () => {
      if (document.visibilityState === "visible") socket.nudge();
    };
    window.addEventListener("online", wake);
    document.addEventListener("visibilitychange", wake);

    // A message the server never acknowledged becomes "failed", with a Retry button.
    const sweep = window.setInterval(() => {
      const stale = findStaleSending(useChatStore.getState().state, Date.now(), ACK_TIMEOUT_MS);
      for (const { conversationId, clientId } of stale) {
        dispatch({
          type: "local/fail", conversationId, clientId,
          reason: "The server did not respond. Try again.",
        });
      }
    }, 2_000);

    return () => {
      window.clearInterval(sweep);
      window.removeEventListener("online", wake);
      document.removeEventListener("visibilitychange", wake);
      batcher.cancel();
      socket.disconnect();
      socketRef.current = null;
    };
  }, [dispatch, queryClient]);

  const send = useCallback(
    (command: ClientCommand) => socketRef.current?.send(encodeCommand(command)) ?? false,
    [],
  );
  const reconnectNow = useCallback(() => {
    const socket = socketRef.current;
    if (!socket) return;
    if (socket.currentStatus === "closed" || socket.currentStatus === "idle") socket.connect();
    else socket.nudge();
  }, []);

  const value = useMemo(() => ({ status, send, reconnectNow }), [status, send, reconnectNow]);
  return <ChatSocketContext.Provider value={value}>{children}</ChatSocketContext.Provider>;
}

export function useChatSocket(): ChatSocketValue {
  const value = useContext(ChatSocketContext);
  if (!value) throw new Error("useChatSocket must be used inside <ChatSocketProvider>");
  return value;
}
