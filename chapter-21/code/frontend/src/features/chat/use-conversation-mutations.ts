"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { deleteConversationApi, renameConversationApi } from "./api";
import { removeFromList, renameInList, type ConversationSummary } from "./conversations-cache";

const KEY = ["conversations"]; // the list query from Chapter 20

/**
 * The optimistic update recipe, in four steps:
 * 1. onMutate:  stop in-flight refetches (they would overwrite our guess), save the old
 *               data, and write the new data into the cache. The UI changes instantly.
 * 2. onError:   put the saved data back. The user sees the change undone.
 * 3. onSettled: refetch from the server, so the cache ends up matching the truth.
 */
function useOptimisticListMutation<TVars extends { id: string }>(
  mutationFn: (vars: TVars) => Promise<unknown>,
  apply: (list: ConversationSummary[], vars: TVars) => ConversationSummary[],
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn,
    onMutate: async (vars: TVars) => {
      await queryClient.cancelQueries({ queryKey: KEY });
      const previous = queryClient.getQueryData<ConversationSummary[]>(KEY);
      queryClient.setQueryData<ConversationSummary[]>(KEY, (old) =>
        old ? apply(old, vars) : old,
      );
      return { previous };
    },
    onError: (_error, _vars, context) => {
      if (context?.previous) queryClient.setQueryData(KEY, context.previous);
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: KEY }),
  });
}

export const useRenameConversation = () =>
  useOptimisticListMutation(
    ({ id, title }: { id: string; title: string }) => renameConversationApi(id, title),
    (list, { id, title }) => renameInList(list, id, title),
  );

export const useDeleteConversation = () =>
  useOptimisticListMutation(
    ({ id }: { id: string }) => deleteConversationApi(id),
    (list, { id }) => removeFromList(list, id),
  );
