import { waitForActivation, type SubscriptionStatus } from "./checkoutPolling";

function fakeTime() {
  let t = 0;
  return { now: () => t, sleep: async (ms: number) => { t += ms; } };
}
const script = (...results: Array<SubscriptionStatus | Error>) => {
  let i = 0;
  return jest.fn(async () => {
    const r = results[Math.min(i++, results.length - 1)];
    if (r instanceof Error) throw r;
    return r;
  });
};

describe("waitForActivation", () => {
  it("returns active as soon as the webhook has landed, without waiting needlessly", async () => {
    const time = fakeTime();
    const fetch = script("pending", "pending", "active");
    expect(await waitForActivation(fetch, { ...time, intervalMs: 1000 })).toBe("active");
    expect(fetch).toHaveBeenCalledTimes(3);
    expect(time.now()).toBe(2000);                       // two sleeps, nothing more
  });

  it("returns failed immediately when the payment failed", async () => {
    expect(await waitForActivation(script("failed"), fakeTime())).toBe("failed");
  });

  it("gives up with a timeout when the webhook never arrives", async () => {
    const time = fakeTime();
    expect(await waitForActivation(script("pending"), { ...time, intervalMs: 1000, timeoutMs: 5000 })).toBe("timeout");
    expect(time.now()).toBeGreaterThan(4999);
  });

  it("survives a single network blip", async () => {
    const fetch = script(new Error("offline"), "active");
    expect(await waitForActivation(fetch, fakeTime())).toBe("active");
  });

  it("gives up on the error after repeated failures instead of polling forever", async () => {
    const fetch = script(new Error("server down"));
    await expect(waitForActivation(fetch, { ...fakeTime(), maxConsecutiveErrors: 3 })).rejects.toThrow("server down");
    expect(fetch).toHaveBeenCalledTimes(3);
  });

  it("a good answer resets the error count", async () => {
    const fetch = script(new Error("a"), new Error("b"), "pending", new Error("c"), new Error("d"), "active");
    expect(await waitForActivation(fetch, { ...fakeTime(), maxConsecutiveErrors: 3 })).toBe("active");
  });
});
