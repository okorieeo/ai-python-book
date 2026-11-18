// A server that accepts only the access token "A2" and rotates refresh tokens.
const rotatingServer: Handler = (url, init) => {
  if (url.endsWith("/auth/token/refresh")) {
    return json(200, { access: "A2", refresh: "R2" });
  }
  const auth = (init.headers as Record<string, string>).Authorization;
  return auth === "Bearer A2"
    ? json(200, { ok: true })
    : json(401, { error: { code: "token_expired", message: "The token is expired." } });
};

it("refreshes on 401, retries once and keeps the ROTATED refresh token", async () => {
  const { client, store, storage, calls, onSignedOut } = await setup(rotatingServer);
  expect(await client.get("/me")).toEqual({ ok: true });
  expect(calls.map((c) => c.url.split("/api/v1")[1])).toEqual([
    "/me", "/auth/token/refresh", "/me",
  ]);
  expect(header(calls[2], "Authorization")).toBe("Bearer A2");
  expect(storage.data[REFRESH_KEY]).toBe("R2");
  expect(onSignedOut).not.toHaveBeenCalled();
});

it("three parallel 401s cause exactly ONE refresh", async () => {
  const { client, calls } = await setup(rotatingServer);
  await Promise.all([client.get("/a"), client.get("/b"), client.get("/c")]);
  expect(calls.filter((c) => c.url.endsWith("/auth/token/refresh"))).toHaveLength(1);
});

it("does NOT sign out when the phone is offline during the refresh", async () => {
  // ...the refresh call throws "Network request failed"
  await expect(client.get("/me")).rejects.toBeInstanceOf(NetworkError);
  expect(onSignedOut).not.toHaveBeenCalled();
  expect(storage.data[REFRESH_KEY]).toBe("R1"); // still signed in
});
