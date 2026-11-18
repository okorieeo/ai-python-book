import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { createChaosFetch } from '../lib/dev/chaosFetch';
import { ApiError } from '../lib/net/errors';
import { fetchWithTimeout } from '../lib/net/fetchWithTimeout';
import { json } from './helpers';

const base: typeof fetch = async () => json({ ok: true });

describe('createChaosFetch', () => {
  it('passes requests through when no chaos is configured', async () => {
    const res = await createChaosFetch({ base })('https://x.test/');
    assert.deepEqual(await res.json(), { ok: true });
  });

  it('behaves like a phone without network', async () => {
    let offline = true;
    const chaos = createChaosFetch({ base, offline: () => offline });
    await assert.rejects(chaos('https://x.test/'), /Network request failed/);
    offline = false;
    assert.equal((await chaos('https://x.test/')).status, 200);
  });

  it('fails a chosen share of requests: dropped connections and 503s', async () => {
    const rolls = [0.5, 0.1, 0.5, 0.9]; // per request: a latency roll, then a failure roll
    const chaos = createChaosFetch({ base, failureRate: 0.6, random: () => rolls.shift() ?? 0.99, delay: async () => {} });
    await assert.rejects(chaos('https://x.test/'), TypeError);
    const second = await chaos('https://x.test/'); // failure roll 0.9 > 0.6: passes
    assert.equal(second.status, 200);
  });

  it('answers 503 with Retry-After on the second kind of failure', async () => {
    const rolls = [0.5, 0.4]; // latency roll, failure roll: between rate/2 and rate
    const chaos = createChaosFetch({ base, failureRate: 0.6, random: () => rolls.shift() ?? 0.99, delay: async () => {} });
    const res = await chaos('https://x.test/');
    assert.equal(res.status, 503);
    assert.equal(res.headers.get('retry-after'), '1');
  });

  it('adds latency that fetchWithTimeout correctly reports as a timeout', async () => {
    const slow = createChaosFetch({ base, latencyMs: [5_000, 5_000] });
    await assert.rejects(fetchWithTimeout('https://x.test/', { timeoutMs: 30, fetchImpl: slow }), (e: ApiError) => e.kind === 'timeout');
  });
});
