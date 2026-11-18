import { useCallback, useEffect, useRef, useState } from "react";
import { listDocuments } from "./api";
import type { DocumentItem } from "./types";

/** Loads the documents and keeps polling every 3 seconds while any of them is still being processed. */
export function useDocuments() {
  const [docs, setDocs] = useState<DocumentItem[]>([]);
  const [loading, setLoading] = useState(true);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const refresh = useCallback(async () => {
    try {
      const items = await listDocuments();
      setDocs(items);
      const busy = items.some((d) => d.status === "uploaded" || d.status === "processing");
      clearTimeout(timer.current);
      if (busy) timer.current = setTimeout(refresh, 3000);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    return () => clearTimeout(timer.current);   // stop polling when the component goes away
  }, [refresh]);

  return { docs, loading, refresh };
}
