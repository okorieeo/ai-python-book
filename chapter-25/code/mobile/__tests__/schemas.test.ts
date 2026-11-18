import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { parseMessagePage } from '../lib/api/schemas';
import { ApiError } from '../lib/net/errors';
import { requestJson } from '../lib/net/fetchWithTimeout';
import { json } from './helpers';

const good = { results: [{ id: 'm1', role: 'user', content: 'hi', created_at: '2026-11-04T10:00:00Z', client_id: null }], next: null };

describe('parseMessagePage', () => {
  it('accepts the shape the API promises', () => {
    const page = parseMessagePage(good);
    assert.equal(page.messages[0].content, 'hi');
    assert.equal(page.next, null);
  });

  it('turns a missing field into one clear error at the boundary', async () => {
    const broken = { results: [{ id: 'm1', role: 'user', created_at: 'x' }] }; // no "content"
    assert.throws(() => parseMessagePage(broken));
    await assert.rejects(
      requestJson('https://x.test/', { fetchImpl: async () => json(broken), parse: parseMessagePage }),
      (e: ApiError) => e.kind === 'parse',
    );
  });

  it('rejects an unknown role instead of rendering it', () => {
    assert.throws(() => parseMessagePage({ results: [{ ...good.results[0], role: 'admin' }] }));
  });
});
