import { MemoryStore } from "../src/storage";
import { TokenStore, redactToken } from "../src/tokenStore";

const good = { access: "access-token-123", refresh: "refresh-token-456", accessExpiresAt: 1_700_000_000_000 };

test("tokens survive a round trip through storage", async () => {
  const store = new MemoryStore();
  await new TokenStore(store).set(good);
  expect(await new TokenStore(store).get()).toEqual(good); // a fresh instance reads what was saved
});

test("nothing stored means signed out", async () => {
  expect(await new TokenStore(new MemoryStore()).get()).toBeNull();
});

test("corrupt or malformed data is removed and treated as signed out", async () => {
  for (const bad of ["not json", "{}", '{"access":"a"}', '{"access":"","refresh":"r"}', "null", "[]", '{"access":1,"refresh":2}']) {
    const store = new MemoryStore();
    store.data.set("auth.tokens.v1", bad);
    const tokens = new TokenStore(store);
    expect(await tokens.get()).toBeNull();
    expect(store.data.has("auth.tokens.v1")).toBe(false);
  }
});

test("malformed tokens are refused instead of stored", async () => {
  const tokens = new TokenStore(new MemoryStore());
  await expect(tokens.set({ access: "", refresh: "x" })).rejects.toThrow("malformed");
  expect(await tokens.get()).toBeNull();
});

test("clear signs the user out everywhere", async () => {
  const store = new MemoryStore();
  const tokens = new TokenStore(store);
  await tokens.set(good);
  await tokens.clear();
  expect(await tokens.get()).toBeNull();
  expect(store.data.size).toBe(0);
});

test("storage is read once, then served from memory", async () => {
  const store = new MemoryStore();
  await store.setItem("auth.tokens.v1", JSON.stringify(good));
  const spy = jest.spyOn(store, "getItem");
  const tokens = new TokenStore(store);
  await tokens.get();
  await tokens.get();
  await tokens.get();
  expect(spy).toHaveBeenCalledTimes(1);
});

test("redactToken never reveals the token", () => {
  const shown = redactToken("abcdef-secret-value");
  expect(shown).toBe("abcd...(19 chars)");
  expect(shown).not.toContain("secret");
  expect(redactToken(null)).toBe("(none)");
});
