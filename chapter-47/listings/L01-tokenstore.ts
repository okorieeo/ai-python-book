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
