  it("keeps the access token in memory and the refresh token in storage", async () => {
    const storage = memoryStorage();
    const store = createTokenStore(storage);
    await store.setTokens({ access: "A1", refresh: "R1" });
    expect(store.getAccess()).toBe("A1");
    expect(storage.data).toEqual({ [REFRESH_KEY]: "R1" }); // the access token is NOT here
  });

  it("survives an app restart with the refresh token only", async () => {
    const storage = memoryStorage();
    await createTokenStore(storage).setTokens({ access: "A1", refresh: "R1" });
    const afterRestart = createTokenStore(storage); // a new process, same Keychain
    expect(afterRestart.getAccess()).toBeNull();
    expect(await afterRestart.getRefresh()).toBe("R1");
  });
