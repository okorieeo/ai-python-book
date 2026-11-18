import type { KeyValueStore } from "./storage";

export interface Tokens {
  access: string;
  refresh: string;
  /** When the access token stops working, in milliseconds since 1970. Optional. */
  accessExpiresAt?: number;
}

const DEFAULT_KEY = "auth.tokens.v1";

function isTokens(value: unknown): value is Tokens {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    typeof v.access === "string" &&
    v.access.length > 0 &&
    typeof v.refresh === "string" &&
    v.refresh.length > 0 &&
    (v.accessExpiresAt === undefined || typeof v.accessExpiresAt === "number")
  );
}

/**
 * Keeps the access and refresh tokens in secure storage as one small JSON value.
 * Back `store` with expo-secure-store (the Keychain on iOS, an encrypted store on Android),
 * never with AsyncStorage: AsyncStorage is plain text on the device.
 */
export class TokenStore {
  private cache: Tokens | null = null;
  private loaded = false;

  constructor(
    private readonly store: KeyValueStore,
    private readonly key: string = DEFAULT_KEY,
  ) {}

  async get(): Promise<Tokens | null> {
    if (this.loaded) return this.cache;
    const raw = await this.store.getItem(this.key);
    this.loaded = true;
    if (raw === null) return (this.cache = null);
    try {
      const parsed: unknown = JSON.parse(raw);
      if (isTokens(parsed)) return (this.cache = parsed);
    } catch {
      // fall through: corrupt data is treated as "signed out"
    }
    await this.store.removeItem(this.key);
    return (this.cache = null);
  }

  async set(tokens: Tokens): Promise<void> {
    if (!isTokens(tokens)) throw new Error("Refusing to store malformed tokens");
    await this.store.setItem(this.key, JSON.stringify(tokens));
    this.cache = tokens;
    this.loaded = true;
  }

  async clear(): Promise<void> {
    await this.store.removeItem(this.key);
    this.cache = null;
    this.loaded = true;
  }
}

/** For logs: shows that a token exists, never the token. */
export function redactToken(token: string | null | undefined): string {
  if (!token) return "(none)";
  return `${token.slice(0, 4)}...(${token.length} chars)`;
}
