import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { ApiError } from '../lib/net/errors';
import { fetchWithTimeout, parseRetryAfter, requestJson } from '../lib/net/fetchWithTimeout';
import { abortError, hangingFetch, json } from './helpers';

const kind = (expected: string) => (e: unknown) => e instanceof ApiError && e.kind === expected;

describe('fetchWithTimeout', () => {
  it('gives up on a connection that never answers', async () => {
    const started = Date.now();
    await assert.rejects(fetchWithTimeout('https://x.test/', { timeoutMs: 30, fetchImpl: hangingFetch }), kind('timeout'));
    assert.ok(Date.now() - started < 500);
  });

  it('reports a cancellation from outside as "aborted", not "timeout"', async () => {
    const controller = new AbortController();
    setTimeout(() => controller.abort(), 10);
    await assert.rejects(
      fetchWithTimeout('https://x.test/', { timeoutMs: 5_000, signal: controller.signal, fetchImpl: hangingFetch }),
      kind('aborted'),
    );
  });

  it('does not even start when the signal is already aborted', async () => {
    let called = false;
    const controller = new AbortController();
    controller.abort();
    await assert.rejects(
      fetchWithTimeout('https://x.test/', { signal: controller.signal, fetchImpl: async () => ((called = true), json({})) }),
      kind('aborted'),
    );
    assert.equal(called, false);
  });

  it('turns a dropped connection into a "network" error', async () => {
    const failing: typeof fetch = async () => {
      throw new TypeError('Network request failed');
    };
    await assert.rejects(fetchWithTimeout('https://x.test/', { fetchImpl: failing }), kind('network'));
  });
});

describe('parseRetryAfter', () => {
  it('understands seconds, dates and garbage', () => {
    assert.equal(parseRetryAfter('30'), 30_000);
    assert.equal(parseRetryAfter(' 5 '), 5_000);
    const now = Date.parse('2026-11-04T10:00:00Z');
    assert.equal(parseRetryAfter('Wed, 04 Nov 2026 10:00:45 GMT', now), 45_000);
    assert.equal(parseRetryAfter('Wed, 04 Nov 2026 09:00:00 GMT', now), 0);
    assert.equal(parseRetryAfter('soon'), undefined);
    assert.equal(parseRetryAfter(null), undefined);
  });
});

describe('requestJson', () => {
  it('returns parsed JSON and runs the validator', async () => {
    const data = await requestJson<{ n: number }>('https://x.test/', {
      fetchImpl: async () => json({ n: 7 }),
      parse: (d) => d as { n: number },
    });
    assert.deepEqual(data, { n: 7 });
  });

  it('keeps the status and Retry-After of an error response, but not an HTML error page', async () => {
    const page = new Response('<html>Bad gateway</html>', { status: 503, headers: { 'Retry-After': '2' } });
    await assert.rejects(requestJson('https://x.test/', { fetchImpl: async () => page }), (e: ApiError) => {
      return e.kind === 'http' && e.status === 503 && e.retryAfterMs === 2000 && e.body === undefined;
    });
  });

  it('treats a 200 answer that is not JSON (a captive portal) as unreadable', async () => {
    const portal = new Response('<html>Sign in to Wi-Fi</html>', { status: 200 });
    await assert.rejects(requestJson('https://x.test/', { fetchImpl: async () => portal }), kind('parse'));
  });

  it('rejects JSON of the wrong shape with one clear error', async () => {
    await assert.rejects(
      requestJson('https://x.test/', {
        fetchImpl: async () => json({ unexpected: true }),
        parse: (d) => {
          if (typeof (d as { id?: unknown }).id !== 'string') throw new Error('missing id');
          return d;
        },
      }),
      kind('parse'),
    );
  });

  it('returns undefined for 204 No Content', async () => {
    const result = await requestJson('https://x.test/', { fetchImpl: async () => new Response(null, { status: 204 }) });
    assert.equal(result, undefined);
  });

  it('the deadline also covers a body that stalls after the headers arrived', async () => {
    const stalling: typeof fetch = async (_url, init) =>
      ({
        ok: true,
        status: 200,
        headers: new Headers(),
        text: () => new Promise<string>((_res, rej) => init?.signal?.addEventListener('abort', () => rej(abortError()))),
      }) as unknown as Response;
    await assert.rejects(requestJson('https://x.test/', { timeoutMs: 30, fetchImpl: stalling }), kind('timeout'));
  });
});
