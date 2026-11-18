import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { ApiError, isRetryable, isUnauthorized, userMessage } from '../lib/net/errors';
import { httpError, networkError, timeoutError } from './helpers';

describe('isRetryable', () => {
  it('retries network failures and timeouts only when repeating is safe', () => {
    assert.equal(isRetryable(networkError(), { idempotent: true }), true);
    assert.equal(isRetryable(timeoutError(), { idempotent: true }), true);
    assert.equal(isRetryable(networkError(), { idempotent: false }), false);
    assert.equal(isRetryable(timeoutError(), { idempotent: false }), false);
  });

  it('retries "try again later" statuses and nothing else', () => {
    for (const status of [408, 429, 500, 502, 503, 504]) {
      assert.equal(isRetryable(httpError(status), { idempotent: true }), true, String(status));
    }
    for (const status of [400, 401, 403, 404, 409, 413, 422]) {
      assert.equal(isRetryable(httpError(status), { idempotent: true }), false, String(status));
    }
  });

  it('never retries cancellations, unreadable responses or unknown errors', () => {
    assert.equal(isRetryable(new ApiError({ kind: 'aborted' }), { idempotent: true }), false);
    assert.equal(isRetryable(new ApiError({ kind: 'parse' }), { idempotent: true }), false);
    assert.equal(isRetryable(new TypeError('boom'), { idempotent: true }), false);
  });
});

describe('isUnauthorized', () => {
  it('is true only for HTTP 401', () => {
    assert.equal(isUnauthorized(httpError(401)), true);
    assert.equal(isUnauthorized(httpError(403)), false);
    assert.equal(isUnauthorized(networkError()), false);
  });
});

describe('userMessage', () => {
  it('never leaks status codes or technical words to the screen', () => {
    const errors = [networkError(), timeoutError(), httpError(500), httpError(404), httpError(429), httpError(422), new ApiError({ kind: 'parse' })];
    for (const error of errors) {
      const text = userMessage(error);
      assert.doesNotMatch(text, /\d{3}|exception|undefined|null|ApiError/i, text);
    }
  });

  it('says something useful for the common cases', () => {
    assert.match(userMessage(networkError()), /offline/i);
    assert.match(userMessage(timeoutError()), /slow/i);
    assert.match(userMessage(httpError(401)), /sign in/i);
    assert.match(userMessage(new Error('anything')), /try again/i);
  });
});
