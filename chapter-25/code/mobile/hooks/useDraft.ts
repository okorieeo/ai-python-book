import AsyncStorage from '@react-native-async-storage/async-storage';
import { useCallback, useEffect, useRef, useState } from 'react';
import { createDraftStore } from '../lib/offline/drafts';

const drafts = createDraftStore(AsyncStorage);

/** Text of a message the user has not sent yet. Saved a moment after typing stops; restored on return. */
export function useDraft(conversationId: string) {
  const [text, setText] = useState('');
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    let cancelled = false;
    void drafts.get(conversationId).then((saved) => {
      if (!cancelled && saved) setText(saved);
    });
    return () => {
      cancelled = true; // the screen closed before the read finished: do not set state
      if (timer.current) clearTimeout(timer.current);
    };
  }, [conversationId]);

  const update = useCallback(
    (next: string) => {
      setText(next);
      if (timer.current) clearTimeout(timer.current);
      timer.current = setTimeout(() => void drafts.set(conversationId, next), 400);
    },
    [conversationId],
  );

  const clear = useCallback(() => {
    if (timer.current) clearTimeout(timer.current);
    setText('');
    void drafts.clear(conversationId);
  }, [conversationId]);

  return { text, update, clear };
}
