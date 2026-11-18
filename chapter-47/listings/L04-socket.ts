private handleClosed(code: number): void {
  const wasStable = this.state === "open" && (this.o.now ?? Date.now)() - this.openedAt >= (this.o.stableAfterMs ?? 10_000);
  this.teardown(1000, "closed");
  if (code === CLOSE_AUTH_FAILED) {
    this.wantConnected = false;
    this.setState("closed");
    for (const l of this.authFailedListeners) l(); // refresh the token, then call connect() again
    return;
  }
  if (!this.wantConnected) {
    this.setState("closed");
    return;
  }
  if (wasStable) this.attempt = 0;
  const base = this.o.baseDelayMs ?? 1_000;
  const ceiling = Math.min(this.o.maxDelayMs ?? 30_000, base * 2 ** this.attempt);
  const delay = Math.round(ceiling / 2 + (ceiling / 2) * (this.o.random ?? Math.random)());
  this.attempt++;
  this.setState("waiting");
  this.schedule(() => {
    if (this.wantConnected && this.state === "waiting") void this.open();
  }, delay);
}
