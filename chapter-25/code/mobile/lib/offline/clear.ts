import AsyncStorage from '@react-native-async-storage/async-storage';
import { queryClient, persister } from '../query/client';
import { createDraftStore } from './drafts';
import { outbox } from './outboxInstance';

/** Call on sign-out. Everything we saved for the previous user must go before the next one signs in. */
export async function clearOfflineData(): Promise<void> {
  await queryClient.cancelQueries();
  queryClient.clear();
  await persister.removeClient();
  await outbox.clear();
  await createDraftStore(AsyncStorage).clearAll();
}
