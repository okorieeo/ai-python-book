// Where the tokens live.
//   access token   in MEMORY only. It lives 15 minutes and dies with the app.
//   refresh token  in the secure store (Keychain on iOS, Keystore on Android).
// The storage is passed in, so the tests can use a plain object instead of a phone.

export interface KeyValueStorage {
  getItem(key: string): Promise<string | null>;
  setItem(key: string, value: string): Promise<void>;
  removeItem(key: string): Promise<void>;
}

export const REFRESH_KEY = "auth.refresh_token"; // keys: letters, digits . - _ only

export interface TokenPair {
  access: string;
  refresh?: string; // the server rotates it on every refresh, so it may be new
}

export function createTokenStore(storage: KeyValueStorage) {
  let access: string | null = null;

  return {
    getAccess: () => access,

    getRefresh: () => storage.getItem(REFRESH_KEY),

    async setTokens(tokens: TokenPair) {
      access = tokens.access;
      if (tokens.refresh) await storage.setItem(REFRESH_KEY, tokens.refresh);
    },

    async clear() {
      access = null;
      await storage.removeItem(REFRESH_KEY);
    },
  };
}

export type TokenStore = ReturnType<typeof createTokenStore>;
