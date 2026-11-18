import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "../api";
import { describeError } from "../api/errors";
import type { Document } from "../api/types";

const PAGE = 20;

export function useDocuments() {
  const [items, setItems] = useState<Document[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const busy = useRef(false); // one request at a time: onEndReached fires in bursts

  const load = useCallback(async (reset: boolean, offset: number) => {
    if (busy.current) return;
    busy.current = true;
    try {
      const page = await api.documents(offset, PAGE);
      setItems((old) => (reset ? page.results : [...old, ...page.results]));
      setTotal(page.count);
      setError(null);
    } catch (e) {
      setError(describeError(e));
    } finally {
      busy.current = false;
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => void load(true, 0), [load]);

  return {
    items,
    loading,
    refreshing,
    error,
    hasMore: items.length < total,
    refresh: () => {
      setRefreshing(true);
      return load(true, 0);
    },
    loadMore: () => (items.length < total ? load(false, items.length) : undefined),
    remove: (id: string) => {
      setItems((old) => old.filter((d) => d.id !== id));
      setTotal((n) => n - 1);
    },
    add: (doc: Document) => setItems((old) => (old.some((d) => d.id === doc.id) ? old : [doc, ...old])),
  };
}
