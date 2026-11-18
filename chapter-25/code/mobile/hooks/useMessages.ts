import { queryOptions, useQuery } from '@tanstack/react-query';
import { useMemo } from 'react';
import { apiRequest } from '../lib/api/client';
import { parseMessagePage } from '../lib/api/schemas';
import { mergeMessages } from '../lib/offline/messages';
import { useOutboxItems } from './useOutbox';

export const messagesQuery = (conversationId: string) =>
  queryOptions({
    queryKey: ['messages', conversationId] as const,
    queryFn: async ({ signal }) =>
      (await apiRequest(`/conversations/${conversationId}/messages/`, { signal, parse: parseMessagePage })).messages,
    staleTime: 15_000,
  });

export function useMessages(conversationId: string) {
  const query = useQuery(messagesQuery(conversationId));
  const queued = useOutboxItems();
  const messages = useMemo(() => mergeMessages(query.data ?? [], queued, conversationId), [query.data, queued, conversationId]);

  return {
    messages,
    /** Nothing to show yet at all: show a skeleton. */
    isLoading: query.isPending && query.fetchStatus !== 'paused',
    /** We have saved data but cannot refresh it right now. */
    isShowingSavedData: query.data !== undefined && query.fetchStatus === 'paused',
    isRefreshing: query.isFetching && query.data !== undefined,
    /** Only an error with nothing to show is a screen-level error. */
    error: query.data === undefined ? query.error : null,
    lastUpdatedAt: query.dataUpdatedAt || null,
    refetch: query.refetch,
  };
}
