"use client";

import { useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo } from "react";
import { fetchMessages } from "./api";
import { mergeForDisplay } from "./chat-state";
import { useChatSocket } from "./chat-socket-provider";
import { useChatStore } from "./chat-store";

/** Everything a chat screen needs: messages, connection state, and the three actions. */
export function useChatController(conversationId: string) {
  const { status: connection, send: sendCommand, reconnectNow } = useChatSocket();
  const dispatch = useChatStore((s) => s.dispatch);
  const live = useChatStore((s) => s.state[conversationId]);

  const history = useQuery({
    queryKey: ["messages", conversationId],
    queryFn: () => fetchMessages(conversationId),
  });

  const messages = useMemo(
    () => mergeForDisplay(history.data ?? [], live?.messages ?? []),
    [history.data, live?.messages],
  );

  // Forget local copies once the server's history contains them.
  // (When nothing changes the reducer returns the same state: no re-render.)
  useEffect(() => {
    if (!history.data || !live?.messages.length) return;
    dispatch({ type: "prune", conversationId, confirmedIds: history.data.map((m) => m.id) });
  }, [history.data, live?.messages, conversationId, dispatch]);

  const transmit = useCallback(
    (clientId: string, content: string, attachmentIds: string[]) => {
      const sent = sendCommand({
        type: "message.send",
        conversation_id: conversationId,
        client_id: clientId, // the server uses it to ignore duplicates when we retry
        content,
        attachment_ids: attachmentIds.length > 0 ? attachmentIds : undefined,
      });
      if (!sent) {
        dispatch({
          type: "local/fail", conversationId, clientId,
          reason: "You are offline. Check your connection and try again.",
        });
      }
    },
    [conversationId, dispatch, sendCommand],
  );

  const send = useCallback(
    (content: string, attachmentIds: string[] = []) => {
      const clientId = crypto.randomUUID(); // needs https or localhost
      dispatch({
        type: "local/send", conversationId, clientId, content,
        now: Date.now(), attachmentIds,
      });
      transmit(clientId, content, attachmentIds);
    },
    [conversationId, dispatch, transmit],
  );

  const retry = useCallback(
    (clientId: string) => {
      const message = live?.messages.find((m) => m.id === clientId || m.clientId === clientId);
      if (!message) return;
      dispatch({ type: "local/resend", conversationId, clientId, now: Date.now() });
      transmit(message.clientId ?? message.id, message.content, message.attachmentIds ?? []);
    },
    [conversationId, dispatch, live?.messages, transmit],
  );

  const stop = useCallback(
    () => void sendCommand({ type: "generation.stop", conversation_id: conversationId }),
    [conversationId, sendCommand],
  );

  const dismissError = useCallback(
    () => dispatch({ type: "local/dismiss_error", conversationId }),
    [conversationId, dispatch],
  );

  return {
    messages,
    connection,
    reconnectNow,
    loadingHistory: history.isPending,
    historyError: history.isError,
    refetchHistory: history.refetch,
    awaitingReply: live?.awaitingReply ?? false,
    generating: (live?.generatingId ?? null) !== null,
    error: live?.error ?? null,
    send, stop, retry, dismissError,
  };
}
