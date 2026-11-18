import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { ApiError } from '../lib/net/errors';
import { backoffDelay, sleep, withRetry } from '../lib/net/retry';
import { httpError, networkError } from './helpers';

const half = () => 0.5;

/** A sleep that does not wait; it just records how long it was asked to wait. */
function recordingSleep() {
  const delays: number[] = [];
  return { delays, sleep: async (ms: number) => void delays.push(ms) };
}

/** A function that fails with the given errors in turn, then succeeds. */
function flaky<T>(errors: Error[], value: T) {
  let calls = 0;
  return {
    get calls() {
      return calls;
    },
    run: async () => {
      if (calls < errors.length) throw errors[calls++];
      calls++;
      return value;
    },
  };
}

describe('backoffDelay', () => {
  it('doubles the ceiling each attempt until it hits the cap', () => {
    const delays = [0, 1, 2, 3, 4, 5, 6].map((attempt) => backoffDelay(attempt, { random: half }));
    assert.deepEqual(delays, [250, 500, 1000, 2000, 4000, 8000, 15000]);
  });

  it('stays between 0 and the ceiling for any random value', () => {
    for (let attempt = 0; attempt < 12; attempt++) {
      const ceiling = Math.min(30_000, 500 * 2 ** attempt);
      for (const r of [0, 0.001, 0.3, 0.999]) {
        const d = backoffDelay(attempt, { random: () => r });
        assert.ok(d >= 0 && d < ceiling, `attempt ${attempt}, r=${r}, delay=${d}`);
      }
    }
  });
});

describe('withRetry', () => {
  it('retries until it works, waiting longer each time', async () => {
    const fn = flaky([networkError(), httpError(503)], 'ok');
    const { delays, sleep: fakeSleep } = recordingSleep();
    const result = await withRetry(fn.run, { idempotent: true, random: half, sleep: fakeSleep });
    assert.equal(result, 'ok');
    assert.equal(fn.calls, 3);
    assert.deepEqual(delays, [250, 500]);
  });

  it('gives up after the allowed retries and throws the last error', async () => {
    const fn = flaky([networkError(), networkError(), networkError(), networkError()], 'never');
    const { sleep: fakeSleep } = recordingSleep();
    await assert.rejects(withRetry(fn.run, { idempotent: true, retries: 2, sleep: fakeSleep }), (e: ApiError) => e.kind === 'network');
    assert.equal(fn.calls, 3); // first try + 2 retries
  });

  it('does not repeat a request that is unsafe to repeat', async () => {
    const fn = flaky([networkError()], 'ok');
    await assert.rejects(withRetry(fn.run, { idempotent: false }));
    assert.equal(fn.calls, 1);
  });

  it('does not retry a request the server rejected as wrong', async () => {
    const fn = flaky([httpError(400)], 'ok');
    await assert.rejects(withRetry(fn.run, { idempotent: true }));
    assert.equal(fn.calls, 1);
  });

  it('waits at least as long as Retry-After says', async () => {
    const fn = flaky([httpError(503, 2000)], 'ok');
    const { delays, sleep: fakeSleep } = recordingSleep();
    await withRetry(fn.run, { idempotent: true, random: half, sleep: fakeSleep });
    assert.deepEqual(delays, [2000]);
  });

  it('refuses to hold a request open for a very long Retry-After', async () => {
    const fn = flaky([httpError(429, 120_000)], 'ok');
    const { delays, sleep: fakeSleep } = recordingSleep();
    await assert.rejects(withRetry(fn.run, { idempotent: true, sleep: fakeSleep }), (e: ApiError) => e.status === 429);
    assert.equal(fn.calls, 1);
    assert.deepEqual(delays, []);
  });

  it('stops early instead of waiting past its time budget', async () => {
    const fn = flaky([networkError(), networkError()], 'ok');
    const { delays, sleep: fakeSleep } = recordingSleep();
    await assert.rejects(withRetry(fn.run, { idempotent: true, random: half, sleep: fakeSleep, deadlineMs: 300, now: () => 0 }));
    assert.deepEqual(delays, [250]); // the second wait (500 ms) would not fit in 300 ms
  });

  it('reports each retry so the UI can say "Trying again..."', async () => {
    const fn = flaky([networkError()], 'ok');
    const seen: number[] = [];
    await withRetry(fn.run, { idempotent: true, random: half, sleep: async () => {}, onRetry: ({ attempt }) => seen.push(attempt) });
    assert.deepEqual(seen, [0]);
  });

  it('stops waiting the moment the caller cancels', async () => {
    const controller = new AbortController();
    const fn = flaky([networkError(), networkError()], 'ok');
    const started = Date.now();
    setTimeout(() => controller.abort(), 20);
    await assert.rejects(
      withRetry(fn.run, { idempotent: true, random: () => 0.99, signal: controller.signal, sleep }),
      (e: ApiError) => e.kind === 'aborted',
    );
    assert.ok(Date.now() - started < 400, 'should not have waited the full backoff');
    assert.equal(fn.calls, 1);
  });
});
