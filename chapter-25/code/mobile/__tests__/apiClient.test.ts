import assert from 'node:assert/strict';
import { beforeEach, describe, it } from 'node:test';
import { apiRequest, configureApi } from '../lib/api/client';
import { ApiError } from '../lib/net/errors';
import { json } from './helpers';

type Call = { url: string; init: RequestInit };

describe('apiRequest', () => {
  let calls: Call[];
  let responses: Array<() => Response>;
  let token: string | null;
  let unauthorized: number;
  const fast = { baseDelayMs: 1, maxDelayMs: 2 };

  beforeEach(() => {
    calls = [];
    responses = [];
    token = 'tok-1';
    unauthorized = 0;
    configureApi({
      baseUrl: 'https://api.test/api/v1',
      getToken: async () => token,
      onUnauthorized: () => void unauthorized++,
      fetchImpl: async (url, init) => {
        calls.push({ url: String(url), init: init ?? {} });
        return (responses.shift() ?? (() => json({ ok: true })))();
      },
    });
  });

  const headers = (i: number) => calls[i].init.headers as Record<string, string>;

  it('adds the token, and only sends a content type when there is a body', async () => {
    await apiRequest('/me/');
    assert.equal(headers(0).Authorization, 'Bearer tok-1');
    assert.equal(headers(0)['Content-Type'], undefined);
    await apiRequest('/x/', { method: 'POST', body: { a: 1 } });
    assert.equal(headers(1)['Content-Type'], 'application/json');
    assert.equal(calls[1].init.body, '{"a":1}');
  });

  it('works without a token (login, health)', async () => {
    token = null;
    await apiRequest('/health/');
    assert.equal(headers(0).Authorization, undefined);
  });

  it('does not retry by default: React Query and the outbox own retrying', async () => {
    responses = [() => new Response('', { status: 503 })];
    await assert.rejects(apiRequest('/x/'), (e: ApiError) => e.status === 503);
    assert.equal(calls.length, 1);
  });

  it('retries a GET when asked to', async () => {
    responses = [() => new Response('', { status: 503 }), () => json({ n: 1 })];
    assert.deepEqual(await apiRequest('/x/', { retries: 2, retry: fast }), { n: 1 });
    assert.equal(calls.length, 2);
  });

  it('never repeats a POST unless it is marked safe', async () => {
    responses = [() => new Response('', { status: 503 }), () => json({})];
    await assert.rejects(apiRequest('/x/', { method: 'POST', body: {}, retries: 2, retry: fast }));
    assert.equal(calls.length, 1);
  });

  it('repeats a POST that carries an idempotency key, with the same body each time', async () => {
    responses = [() => new Response('', { status: 503 }), () => json({ id: 'm1' })];
    const body = { client_id: 'c-1', content: 'hi' };
    await apiRequest('/x/', { method: 'POST', body, idempotent: true, retries: 2, retry: fast });
    assert.equal(calls.length, 2);
    assert.equal(calls[0].init.body, calls[1].init.body);
  });

  it('tells the app when the token was refused', async () => {
    responses = [() => new Response('', { status: 401 })];
    await assert.rejects(apiRequest('/x/'));
    assert.equal(unauthorized, 1);
  });

  it('asks for the token again on each attempt, so a refreshed token is used', async () => {
    responses = [() => new Response('', { status: 503 }), () => json({})];
    const tokens = ['old', 'new'];
    configureApi({
      baseUrl: 'https://api.test',
      getToken: async () => tokens.shift() ?? null,
      fetchImpl: async (url, init) => {
        calls.push({ url: String(url), init: init ?? {} });
        return responses.shift()!();
      },
    });
    await apiRequest('/x/', { retries: 1, retry: fast });
    assert.equal(headers(0).Authorization, 'Bearer old');
    assert.equal(headers(1).Authorization, 'Bearer new');
  });
});
