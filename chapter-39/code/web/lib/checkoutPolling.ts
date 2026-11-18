export type SubscriptionStatus = "pending" | "active" | "failed";
export type PollResult = "active" | "failed" | "timeout";

export interface PollOptions {
  intervalMs?: number;
  timeoutMs?: number;
  maxConsecutiveErrors?: number;
  sleep?: (ms: number) => Promise<void>;     // injected, so tests never really wait
  now?: () => number;                        // injected, so tests control the clock
}

/**
 * After checkout the payment provider calls OUR server (the webhook); the app only learns of it by asking.
 * Poll until the server says the subscription is active. A single failed request is not the end of the world.
 */
export async function waitForActivation(fetchStatus: () => Promise<SubscriptionStatus>, opts: PollOptions = {}): Promise<PollResult> {
  const { intervalMs = 1500, timeoutMs = 60_000, maxConsecutiveErrors = 3 } = opts;
  const sleep = opts.sleep ?? ((ms: number) => new Promise<void>((r) => setTimeout(r, ms)));
  const now = opts.now ?? Date.now;
  const started = now();
  let errors = 0;
  for (;;) {
    try {
      const status = await fetchStatus();
      errors = 0;
      if (status === "active" || status === "failed") return status;
    } catch (err) {
      errors += 1;
      if (errors >= maxConsecutiveErrors) throw err;
    }
    if (now() - started >= timeoutMs) return "timeout";
    await sleep(intervalMs);
  }
}
