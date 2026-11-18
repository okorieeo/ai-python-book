async request<T>(method: string, path: string, opts: RequestOptions = {}): Promise<T> {
  const upper = method.toUpperCase();
  const mayRetry = SAFE_METHODS.has(upper) || Boolean(opts.idempotencyKey);
  for (let attempt = 0; ; attempt++) {
    try {
      return await this.once<T>(upper, path, opts);
    } catch (error) {
      if (!mayRetry || !isRetryable(error) || attempt >= this.opts.maxRetries) throw error;
      await (this.o.sleep ?? defaultSleep)(this.delayFor(attempt, error));
    }
  }
}

private delayFor(attempt: number, error: unknown): number {
  if (error instanceof ApiError && error.retryAfterMs !== undefined) {
    return Math.min(error.retryAfterMs, this.opts.maxDelayMs * 4);
  }
  const ceiling = Math.min(this.opts.maxDelayMs, this.opts.baseDelayMs * 2 ** attempt);
  const random = (this.o.random ?? Math.random)();
  return Math.round(ceiling / 2 + (ceiling / 2) * random); // "equal jitter": never zero, never in lockstep
}
