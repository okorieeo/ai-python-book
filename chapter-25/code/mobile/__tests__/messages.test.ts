import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { mergeMessages, type ServerMessage } from '../lib/offline/messages';
import type { OutboxItem } from '../lib/offline/outbox';

const server = (id: string, at: string, extra: Partial<ServerMessage> = {}): ServerMessage => ({
  id,
  role: 'user',
  content: `server ${id}`,
  created_at: at,
  ...extra,
});

const queued = (id: string, createdAt: number, extra: Partial<OutboxItem> = {}): OutboxItem => ({
  id,
  kind: 'message.send',
  scope: 'c1',
  payload: { content: `local ${id}` },
  createdAt,
  attempts: 0,
  nextAttemptAt: 0,
  status: 'pending',
  ...extra,
});

describe('mergeMessages', () => {
  it('puts waiting messages at the bottom, in the order they were typed', () => {
    const result = mergeMessages(
      [server('s2', '2026-11-04T10:02:00Z'), server('s1', '2026-11-04T10:01:00Z')],
      [queued('q2', 200), queued('q1', 100)],
      'c1',
    );
    assert.deepEqual(result.map((m) => [m.key, m.status]), [
      ['s1', 'sent'],
      ['s2', 'sent'],
      ['q1', 'sending'],
      ['q2', 'sending'],
    ]);
  });

  it('shows a message once: the server copy replaces the local one, with the same React key', () => {
    const result = mergeMessages([server('s1', '2026-11-04T10:00:00Z', { client_id: 'q1' })], [queued('q1', 100)], 'c1');
    assert.equal(result.length, 1);
    assert.equal(result[0].status, 'sent');
    assert.equal(result[0].key, 'q1'); // same key as while it was "sending": no flicker, no remount
  });

  it('keeps failed messages visible with their reason', () => {
    const [m] = mergeMessages([], [queued('q1', 100, { status: 'failed', lastError: 'Too old to send.' })], 'c1');
    assert.equal(m.status, 'failed');
    assert.equal(m.error, 'Too old to send.');
  });

  it('ignores outbox items of other conversations, other kinds and broken payloads', () => {
    const result = mergeMessages(
      [],
      [queued('x1', 1, { scope: 'other' }), queued('x2', 2, { kind: 'conversation.rename' }), queued('x3', 3, { payload: { nope: 1 } })],
      'c1',
    );
    assert.deepEqual(result, []);
  });
});
