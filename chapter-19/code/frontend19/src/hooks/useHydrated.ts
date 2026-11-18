"use client";

import { useSyncExternalStore } from "react";

const subscribe = () => () => {}; // nothing ever changes: we only need two phases

/** false on the server and while hydrating, true afterwards in the browser. */
export function useHydrated() {
  return useSyncExternalStore(
    subscribe,
    () => true,
    () => false,
  );
}
