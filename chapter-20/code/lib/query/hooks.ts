"use client";

import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createApiClient } from "../api/client";
import { createEndpoints } from "../api/endpoints";
import type { Conversation } from "../api/types";
import { prependToFirstPage, replaceItem, type InfiniteData } from "./cache-updates";
import { queryKeys } from "./keys";

const api = createApiClient();
export const endpoints = createEndpoints(api);

type ConversationPages = InfiniteData<Conversation, string | null>;

export function useMe() {
  return useQuery({ queryKey: queryKeys.me, queryFn: ({ signal }) => endpoints.me(signal), staleTime: 5 * 60_000 });
}

/** The conversation list, loaded one cursor page at a time ("Load more"). */
export function useConversations(limit = 20) {
  return useInfiniteQuery({
    queryKey: queryKeys.conversations.list(limit),
    queryFn: ({ pageParam, signal }) => endpoints.listConversations({ limit, cursor: pageParam }, signal),
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage) => lastPage.next ?? undefined,
  });
}

/** Creating a conversation: appears instantly (optimistic), is replaced by the real one, and rolls back on failure. */
export function useCreateConversation(limit = 20) {
  const queryClient = useQueryClient();
  const key = queryKeys.conversations.list(limit);

  return useMutation({
    mutationFn: (input: { title: string; idempotencyKey: string }) => endpoints.createConversation(input.title, input.idempotencyKey),

    onMutate: async (input) => {
      await queryClient.cancelQueries({ queryKey: queryKeys.conversations.all });   // stop in-flight refetches from overwriting us
      const previous = queryClient.getQueryData<ConversationPages>(key);
      const optimistic: Conversation = { id: `tmp_${input.idempotencyKey}`, title: input.title, created_at: new Date().toISOString() };
      queryClient.setQueryData<ConversationPages>(key, (data) => prependToFirstPage(data, optimistic));
      return { previous, optimisticId: optimistic.id };
    },
    onError: (_error, _input, context) => {
      if (context) queryClient.setQueryData(key, context.previous);                  // roll back
    },
    onSuccess: (created, _input, context) => {
      if (context) queryClient.setQueryData<ConversationPages>(key, (data) => replaceItem(data, context.optimisticId, created));
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: queryKeys.conversations.all }),   // reconcile with the server
  });
}
