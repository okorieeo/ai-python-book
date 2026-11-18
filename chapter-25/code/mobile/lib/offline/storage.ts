/**
 * The three methods we need from a key-value store. AsyncStorage already has this shape,
 * so you pass it in as-is; tests pass MemoryStorage. getAllKeys is optional (AsyncStorage has it).
 */
export interface KeyValueStorage {
  getItem(key: string): Promise<string | null>;
  setItem(key: string, value: string): Promise<void>;
  removeItem(key: string): Promise<void>;
  getAllKeys?(): Promise<readonly string[]>;
}

/** In-memory storage for tests. `failWrites` simulates a full disk. */
export class MemoryStorage implements KeyValueStorage {
  readonly data = new Map<string, string>();
  failWrites = false;

  async getItem(key: string): Promise<string | null> {
    return this.data.get(key) ?? null;
  }
  async setItem(key: string, value: string): Promise<void> {
    if (this.failWrites) throw new Error('disk full');
    this.data.set(key, value);
  }
  async removeItem(key: string): Promise<void> {
    this.data.delete(key);
  }
  async getAllKeys(): Promise<readonly string[]> {
    return [...this.data.keys()];
  }
}
