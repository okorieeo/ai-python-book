import AsyncStorage from '@react-native-async-storage/async-storage';
import { apiRequest } from '../api/client';
import { queryClient } from '../query/client';
import { SEND_MESSAGE_KIND, type SendMessagePayload } from './messages';
import { Outbox, type OutboxItem } from './outbox';

/** Sends one queued item. The item id travels as client_id: the server's idempotency key. */
async function sendItem(item: OutboxItem): Promise<unknown> {
  if (item.kind === SEND_MESSAGE_KIND) {
    const { content } = item.payload as SendMessagePayload;
    return apiRequest(`/conversations/${item.scope}/messages/`, {
      method: 'POST',
      body: { client_id: item.id, content },
      idempotent: true,
    });
  }
  throw new Error(`Unknown outbox kind: ${item.kind}`);
}

export const outbox = new Outbox({
  storage: AsyncStorage,
  send: sendItem,
  onSent: (item) => {
    if (item.kind === SEND_MESSAGE_KIND) void queryClient.invalidateQueries({ queryKey: ['messages', item.scope] });
  },
});
