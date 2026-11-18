import { useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';

import { listConversations } from '@/lib/data';
import type { Conversation } from '@/lib/types';

/** Loads the conversation list, and reloads it each time the screen comes into view. */
export function useConversations() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setConversations(await listConversations());
      setError(null);
    } catch {
      setError('Could not load your conversations.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  // Runs when the screen gains focus (also after coming back from a chat).
  useFocusEffect(
    useCallback(() => {
      load();
    }, [load]),
  );

  const refresh = useCallback(() => {
    setRefreshing(true); // shows the pull-to-refresh spinner
    load();
  }, [load]);

  const retry = useCallback(() => {
    setLoading(true);
    load();
  }, [load]);

  return { conversations, loading, refreshing, error, refresh, retry };
}
