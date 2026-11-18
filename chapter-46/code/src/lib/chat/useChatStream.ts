"use client";

import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import { MAX_MESSAGE_LENGTH, parseServerEvent, type ClientEvent } from "./protocol";
import { chatReducer, initialChatState, type ChatMessage, type ChatState } from "./reducer";

export type ConnectionStatus = "connecting" | "open" | "reconnecting";

// The small part of WebSocket we use, so tests can pass a fake.
export interface SocketLike {
  readyState: number;
  send(data: string): void;
  close(): void;
  onopen: ((event: unknown) => void) | null;
  onmessage: ((event: { data: unknown }) => void) | null;
  onclose: ((event: unknown) => void) | null;
}

const OPEN = 1;

export function backoffDelay(
  attempt: number,
  { baseMs = 1000, maxMs = 30000 }: { baseMs?: number; maxMs?: number } = {},
  random: () => number = Math.random,
): number {
  const ceiling = Math.min(maxMs, baseMs * 2 ** attempt);
  return Math.round(ceiling * (0.5 + random() / 2)); // "jitter": no thundering herd after an outage
}

type Options = {
  /** Called before EVERY connection attempt, because tickets are single-use. */
  resolveUrl: () => Promise<string>;
  initialMessages?: ChatMessage[];
  socketFactory?: (url: string) => SocketLike;
  newId?: () => string;
};

const defaultFactory = (url: string): SocketLike => new WebSocket(url) as unknown as SocketLike;
const defaultNewId = () => crypto.randomUUID();

export function useChatStream({
  resolveUrl,
  initialMessages = [],
  socketFactory = defaultFactory,
  newId = defaultNewId,
}: Options): { state: ChatState; connection: ConnectionStatus; send: (content: string) => boolean } {
  const [state, dispatch] = useReducer(chatReducer, initialMessages, (messages): ChatState => ({
    ...initialChatState,
    messages,
  }));
  const [connection, setConnection] = useState<ConnectionStatus>("connecting");
  const socketRef = useRef<SocketLike | null>(null);

  // Keep the latest callbacks without reconnecting every render.
  const resolveRef = useRef(resolveUrl);
  const factoryRef = useRef(socketFactory);
  useEffect(() => {
    resolveRef.current = resolveUrl;
    factoryRef.current = socketFactory;
  });

  useEffect(() => {
    let disposed = false;
    let attempt = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const scheduleRetry = () => {
      if (disposed) return;
      setConnection("reconnecting");
      timer = setTimeout(connect, backoffDelay(attempt++));
    };

    async function connect() {
      let url: string;
      try {
        url = await resolveRef.current();
      } catch {
        scheduleRetry(); // could not get a ticket: try again later
        return;
      }
      if (disposed) return;

      const socket = factoryRef.current(url);
      socketRef.current = socket;
      socket.onopen = () => {
        attempt = 0;
        setConnection("open");
      };
      socket.onmessage = (message) => {
        const event = parseServerEvent(message.data); // anything that does not match is dropped
        if (event) dispatch({ type: "server_event", event });
      };
      socket.onclose = () => {
        if (disposed || socketRef.current !== socket) return;
        socketRef.current = null;
        dispatch({ type: "connection_lost" });
        scheduleRetry();
      };
    }

    void connect();
    return () => {
      disposed = true;
      clearTimeout(timer);
      const socket = socketRef.current;
      socketRef.current = null;
      if (socket) {
        socket.onclose = null; // closing on purpose is not a "lost connection"
        socket.close();
      }
    };
  }, []);

  const send = useCallback(
    (content: string): boolean => {
      const text = content.trim();
      const socket = socketRef.current;
      if (!text || text.length > MAX_MESSAGE_LENGTH) return false;
      if (!socket || socket.readyState !== OPEN || state.status === "streaming") return false;
      // Never queue and auto-resend: a repeated paid request is worse than a visible failure.
      dispatch({ type: "user_sent", id: newId(), content: text });
      const event: ClientEvent = { type: "user_message", content: text };
      socket.send(JSON.stringify(event));
      return true;
    },
    [state.status, newId],
  );

  return { state, connection, send };
}
