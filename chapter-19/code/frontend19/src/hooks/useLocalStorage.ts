"use client";

import { useCallback, useSyncExternalStore } from "react";

const CHANGE_EVENT = "local-storage-change";

function subscribe(callback: () => void) {
  window.addEventListener("storage", callback); // changes from other tabs
  window.addEventListener(CHANGE_EVENT, callback); // changes from this tab
  return () => {
    window.removeEventListener("storage", callback);
    window.removeEventListener(CHANGE_EVENT, callback);
  };
}

/**
 * A string kept in localStorage. It renders `initial` on the server and during
 * hydration, then switches to the stored value, so the HTML always matches.
 */
export function useLocalStorage(key: string, initial: string) {
  const value = useSyncExternalStore(
    subscribe,
    () => {
      try {
        return window.localStorage.getItem(key) ?? initial;
      } catch {
        return initial; // storage blocked (private mode, strict settings)
      }
    },
    () => initial, // what the server renders
  );

  const setValue = useCallback(
    (next: string) => {
      try {
        window.localStorage.setItem(key, next);
      } catch {
        /* ignore: the draft simply will not be remembered */
      }
      window.dispatchEvent(new Event(CHANGE_EVENT));
    },
    [key],
  );

  return [value, setValue] as const;
}
