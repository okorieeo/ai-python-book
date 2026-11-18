import * as Crypto from 'expo-crypto';
import { useCallback } from 'react';
import { SEND_MESSAGE_KIND, type SendMessagePayload } from '../lib/offline/messages';
import { outbox } from '../lib/offline/outboxInstance';

/** Returns a function that saves the message to the outbox (instantly) and starts sending it. */
export function useSendMessage(conversationId: string) {
  return useCallback(
    async (text: string): Promise<void> => {
      const content = text.trim();
      if (!content) return;
      const payload: SendMessagePayload = { content };
      await outbox.enqueue({ id: Crypto.randomUUID(), kind: SEND_MESSAGE_KIND, scope: conversationId, payload });
      void outbox.flush(); // the UI already shows the message as "sending"
    },
    [conversationId],
  );
}
