private async runFlush(): Promise<FlushResult> {
  await this.load();
  const result: FlushResult = { sent: 0, failed: 0, remaining: 0, stoppedBecause: "done" };
  if (this.o.isOnline && !this.o.isOnline()) {
    result.stoppedBecause = "offline";
    result.remaining = this.pending().length;
    return result;
  }
  for (const item of [...this.pending()].sort((a, b) => a.createdAt - b.createdAt)) {
    if (!this.items.includes(item)) continue; // replaced or discarded while we were busy
    this.inFlightId = item.id;
    try {
      await this.o.client.request(item.method, item.path, { body: item.body, idempotencyKey: item.idempotencyKey });
      this.items = this.items.filter((i) => i !== item);
      result.sent++;
    } catch (error) {
      item.attempts++;
      if (error instanceof SessionExpiredError) {
        result.stoppedBecause = "signed-out";
        break; // keep everything: it can be sent after the user signs in again
      }
      if (isRetryable(error)) {
        if (item.attempts >= (this.o.maxAttempts ?? 5)) {
          item.status = "failed";
          item.lastError = describe(error);
          result.failed++;
        } else {
          result.stoppedBecause = "network";
          await this.save();
          break; // stop: do not hammer a struggling server, and keep the order
        }
      } else {
        item.status = "failed"; // the server said no (400, 403, 404, 409, 422): retrying cannot help
        item.lastError = describe(error);
        result.failed++;
      }
    } finally {
      this.inFlightId = null;
      await this.save();
    }
  }
  result.remaining = this.pending().length;
  return result;
}
