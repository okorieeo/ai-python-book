import type { KeyValueStorage } from './storage';

const PREFIX = 'draft:';
export const MAX_DRAFT_LENGTH = 8_000;

/** Unsent text, kept on the device so a crash, a call or a swipe-away never loses what the user typed. */
export function createDraftStore(storage: KeyValueStorage) {
  return {
    get: (scope: string) => storage.getItem(PREFIX + scope),

    async set(scope: string, text: string): Promise<void> {
      if (text.trim() === '') return storage.removeItem(PREFIX + scope);
      await storage.setItem(PREFIX + scope, text.slice(0, MAX_DRAFT_LENGTH));
    },

    clear: (scope: string) => storage.removeItem(PREFIX + scope),

    /** Sign-out: drafts are private too. */
    async clearAll(): Promise<void> {
      const keys = (await storage.getAllKeys?.()) ?? [];
      await Promise.all(keys.filter((k) => k.startsWith(PREFIX)).map((k) => storage.removeItem(k)));
    },
  };
}
