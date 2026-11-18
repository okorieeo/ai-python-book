refresh(): Promise<void> {
  if (!this.refreshing) {
    this.refreshing = this.doRefresh().finally(() => {
      this.refreshing = null;
    });
  }
  return this.refreshing;
}

private async doRefresh(): Promise<void> {
  const tokens = await this.o.tokenStore.get();
  if (!tokens) throw new SessionExpiredError();
  let response: ResponseLike;
  try {
    response = await this.send(`${this.o.baseUrl}${this.opts.refreshPath}`, {
      method: "POST",
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      body: JSON.stringify({ refresh: tokens.refresh }),
    });
  } catch (error) {
    throw error; // offline or slow: keep the tokens, the user is NOT signed out
  }
  if ([400, 401, 403].includes(response.status)) {
    await this.o.tokenStore.clear();
    this.o.onSessionExpired?.();
    throw new SessionExpiredError();
  }
  const data = (await this.parse<{ access: string; refresh?: string; expires_in?: number }>(response));
  await this.o.tokenStore.set({
    access: data.access,
    refresh: data.refresh ?? tokens.refresh, // keep the old one if the server does not rotate
    accessExpiresAt: data.expires_in ? (this.o.now ?? Date.now)() + data.expires_in * 1000 : undefined,
  });
}
