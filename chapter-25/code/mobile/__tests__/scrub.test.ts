import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { scrubEvent, scrubText } from '../lib/crash/scrub';

describe('scrubEvent', () => {
  it('removes personal data and secrets, keeps what helps debugging', () => {
    const event = scrubEvent({
      message: 'Request failed with Authorization: Bearer abc.def-123',
      user: { id: 'u-42', email: 'ada@example.com', username: 'ada', ip_address: '1.2.3.4' },
      request: {
        url: 'https://api.example.com/api/v1/conversations/',
        data: { content: 'my private chat message' },
        cookies: 'sessionid=1',
        headers: { Authorization: 'Bearer abc', 'Content-Type': 'application/json' },
      },
      breadcrumbs: [{ message: 'sent Bearer zzz.yyy', data: { request_body: 'secret', status: 201 } }],
    });
    assert.equal(event.message, 'Request failed with Authorization: Bearer [REDACTED]');
    assert.deepEqual(event.user, { id: 'u-42' });
    assert.equal(event.request?.data, undefined);
    assert.equal(event.request?.cookies, undefined);
    assert.deepEqual(event.request?.headers, { 'Content-Type': 'application/json' });
    assert.equal(event.request?.url, 'https://api.example.com/api/v1/conversations/');
    assert.equal(event.breadcrumbs?.[0].message, 'sent Bearer [REDACTED]');
    assert.deepEqual(event.breadcrumbs?.[0].data, { status: 201 });
  });

  it('copes with events that have none of those parts', () => {
    assert.deepEqual(scrubEvent({}), {});
    assert.equal(scrubText('nothing secret here'), 'nothing secret here');
  });
});
