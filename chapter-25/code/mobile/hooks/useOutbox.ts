import { useSyncExternalStore } from 'react';
import { outbox } from '../lib/offline/outboxInstance';

/** The queue as React state. Re-renders only when the queue changes. */
export const useOutboxItems = () => useSyncExternalStore(outbox.subscribe, outbox.getSnapshot, outbox.getSnapshot);
