import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { ApiError } from '../lib/net/errors';
import { cacheBuster, queryRetry, queryRetryDelay, shouldPersistQuery } from '../lib/query/policy';
import { httpError, networkError } from './helpers';

describe('shouldPersistQuery (what may be written to the phone)', () => {
  it('saves successful conversation and message queries', () => {
    assert.equal(shouldPersistQuery(['conversations'], 'success'), true);
    assert.equal(shouldPersistQuery(['messages', 'abc'], 'success'), true);
  });
  it('never saves anything that is not on the allow-list', () => {
    assert.equal(shouldPersistQuery(['auth', 'token'], 'success'), false);
    assert.equal(shouldPersistQuery(['billing'], 'success'), false);
    assert.equal(shouldPersistQuery([], 'success'), false);
    assert.equal(shouldPersistQuery([{ weird: true }], 'success'), false);
  });
  it('never saves errors or half-loaded queries', () => {
    assert.equal(shouldPersistQuery(['messages', 'abc'], 'error'), false);
    assert.equal(shouldPersistQuery(['messages', 'abc'], 'pending'), false);
  });
});

describe('cacheBuster', () => {
  it('changes with the app version and with the cache schema version', () => {
    assert.equal(cacheBuster('1.4.0', 1), '1.4.0:1');
    assert.notEqual(cacheBuster('1.4.0', 1), cacheBuster('1.4.0', 2));
    assert.notEqual(cacheBuster('1.4.0', 1), cacheBuster('1.5.0', 1));
  });
});

describe('queryRetry / queryRetryDelay', () => {
  it('retries transient failures twice, and never a wrong request', () => {
    assert.equal(queryRetry(0, networkError()), true);
    assert.equal(queryRetry(1, httpError(503)), true);
    assert.equal(queryRetry(2, networkError()), false);
    assert.equal(queryRetry(0, httpError(404)), false);
    assert.equal(queryRetry(0, new TypeError('bug')), false);
  });
  it('respects Retry-After', () => {
    assert.equal(queryRetryDelay(0, httpError(429, 5000)), 5000);
    assert.ok(queryRetryDelay(0, new ApiError({ kind: 'network' })) <= 500);
  });
});
