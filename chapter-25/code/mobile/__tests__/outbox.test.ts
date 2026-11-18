import assert from 'node:assert/strict';
import { beforeEach, describe, it } from 'node:test';
import { Outbox, OutboxFullError, type OutboxItem, type OutboxOptions } from '../lib/offline/outbox';
import { MemoryStorage } from '../lib/offline/storage';
import { deferred, httpError, networkError } from './helpers';

const msg = (id: string, scope = 'c1') => ({ id, kind: 'message.send', scope, payload: { content: `text ${id}` } });

describe('Outbox', () => {
  let storage: MemoryStorage;
  let clock: number;
  let sent: string[];
  let behaviour: (item: OutboxItem) => Promise<unknown>;
  let authCalls: number;

  const make = (extra: Partial<OutboxOptions> = {}) =>
    new Outbox({
      storage,
      now: () => clock,
      backoff: { random: () => 0.5 },
      send: (item) => behaviour(item),
      onSent: (item) => void sent.push(item.id),
      onAuthRequired: () => void authCalls++,
      ...extra,
    });

  beforeEach(() => {
    storage = new MemoryStorage();
    clock = 1_000_000;
    sent = [];
    authCalls = 0;
    behaviour = async () => ({ ok: true });
  });

  it('saves what you queue, and a restarted app finds it again', async () => {
    const outbox = make();
    await outbox.enqueue(msg('a'));
    await outbox.enqueue(msg('b'));

    const afterRestart = make();
    await afterRestart.load();
    assert.deepEqual(afterRestart.getSnapshot().map((i) => i.id), ['a', 'b']);
  });

  it('queues the same id only once (the id is the idempotency key)', async () => {
    const outbox = make();
    await outbox.enqueue(msg('a'));
    await outbox.enqueue(msg('a'));
    assert.equal(outbox.getSnapshot().length, 1);
  });

  it('sends in order, removes what was sent and tells the caller', async () => {
    const outbox = make();
    for (const id of ['a', 'b', 'c']) await outbox.enqueue(msg(id));
    const summary = await outbox.flush();
    assert.deepEqual(sent, ['a', 'b', 'c']);
    assert.deepEqual(summary, { sent: 3, failed: 0, pending: 0, blocked: null });
    assert.equal(outbox.getSnapshot().length, 0);
    assert.equal(JSON.parse(storage.data.get('outbox:v1')!).items.length, 0);
  });

  it('hands the item id to send() on every attempt', async () => {
    const ids: string[] = [];
    behaviour = async (item) => {
      ids.push(item.id);
      if (ids.length === 1) throw httpError(503);
    };
    const outbox = make();
    await outbox.enqueue(msg('a'));
    await outbox.flush();
    clock += 60_000;
    await outbox.flush();
    assert.deepEqual(ids, ['a', 'a']);
  });

  it('keeps an item that hit a dead network, and stops trying the others', async () => {
    behaviour = async () => {
      throw networkError();
    };
    const outbox = make();
    await outbox.enqueue(msg('a', 'c1'));
    await outbox.enqueue(msg('b', 'c2'));
    const calls: string[] = [];
    behaviour = async (item) => {
      calls.push(item.id);
      throw networkError();
    };
    const summary = await outbox.flush();
    assert.equal(summary.blocked, 'network');
    assert.deepEqual(calls, ['a']); // b was not even tried: one timeout is enough
    const [a] = outbox.getSnapshot();
    assert.equal(a.attempts, 1);
    assert.equal(a.nextAttemptAt, clock + 250);
  });

  it('does not retry before the backoff time, and does after', async () => {
    let failing = true;
    behaviour = async () => {
      if (failing) throw httpError(503);
    };
    const outbox = make();
    await outbox.enqueue(msg('a'));
    await outbox.flush();
    assert.equal((await outbox.flush()).sent, 0); // too early
    failing = false;
    clock += 1_000;
    assert.equal((await outbox.flush()).sent, 1);
  });

  it('keeps order inside a conversation, but other conversations carry on', async () => {
    const calls: string[] = [];
    behaviour = async (item) => {
      calls.push(item.id);
      if (item.id === 'a1') throw httpError(503);
    };
    const outbox = make();
    await outbox.enqueue(msg('a1', 'A'));
    await outbox.enqueue(msg('a2', 'A'));
    await outbox.enqueue(msg('b1', 'B'));
    await outbox.flush();
    assert.deepEqual(calls, ['a1', 'b1']); // a2 must wait for a1
    assert.deepEqual(sent, ['b1']);
  });

  it('marks a rejected message as failed and keeps sending the next ones', async () => {
    behaviour = async (item) => {
      if (item.id === 'a') throw httpError(400);
    };
    const outbox = make();
    await outbox.enqueue(msg('a'));
    await outbox.enqueue(msg('b'));
    const summary = await outbox.flush();
    assert.deepEqual(summary, { sent: 1, failed: 1, pending: 0, blocked: null });
    const [a] = outbox.getSnapshot();
    assert.equal(a.status, 'failed');
    assert.match(a.lastError ?? '', /check what you entered/i);
  });

  it('stops and keeps everything when the user must sign in again', async () => {
    behaviour = async () => {
      throw httpError(401);
    };
    const outbox = make();
    await outbox.enqueue(msg('a'));
    await outbox.enqueue(msg('b'));
    const summary = await outbox.flush();
    assert.equal(summary.blocked, 'auth');
    assert.equal(authCalls, 1);
    assert.deepEqual(outbox.getSnapshot().map((i) => [i.id, i.status, i.attempts]), [['a', 'pending', 0], ['b', 'pending', 0]]);
  });

  it('waits as long as Retry-After says', async () => {
    behaviour = async () => {
      throw httpError(429, 60_000);
    };
    const outbox = make();
    await outbox.enqueue(msg('a'));
    await outbox.flush();
    assert.equal(outbox.getSnapshot()[0].nextAttemptAt, clock + 60_000);
  });

  it('gives up after too many attempts but never deletes the message', async () => {
    behaviour = async () => {
      throw httpError(503);
    };
    const outbox = make({ maxAttempts: 3 });
    await outbox.enqueue(msg('a'));
    for (let i = 0; i < 3; i++) await outbox.flush({ force: true });
    const [a] = outbox.getSnapshot();
    assert.equal(a.status, 'failed');
    assert.match(a.lastError ?? '', /several tries/i);
  });

  it('does not send messages that are too old', async () => {
    const outbox = make({ maxAgeMs: 1000 });
    await outbox.enqueue(msg('a'));
    clock += 5_000;
    await outbox.flush();
    assert.deepEqual(sent, []);
    assert.equal(outbox.getSnapshot()[0].status, 'failed');
  });

  it('lets the user retry or discard a failed message', async () => {
    let reject = true;
    behaviour = async () => {
      if (reject) throw httpError(400);
    };
    const outbox = make();
    await outbox.enqueue(msg('a'));
    await outbox.enqueue(msg('b'));
    await outbox.flush();
    reject = false;
    await outbox.retry('a');
    assert.equal(outbox.getSnapshot()[0].status, 'pending');
    assert.equal(outbox.getSnapshot()[0].lastError, undefined);
    await outbox.flush();
    assert.ok(sent.includes('a'));

    await outbox.enqueue(msg('c'));
    await outbox.discard('c');
    assert.deepEqual(outbox.getSnapshot().map((i) => [i.id, i.status]), [['b', 'failed']]); // b was never retried
  });

  it('refuses to grow without limit', async () => {
    const outbox = make({ maxItems: 2 });
    await outbox.enqueue(msg('a'));
    await outbox.enqueue(msg('b'));
    await assert.rejects(outbox.enqueue(msg('c')), OutboxFullError);
  });

  it('does not pretend to have queued something it could not save', async () => {
    const outbox = make();
    await outbox.load();
    storage.failWrites = true;
    await assert.rejects(outbox.enqueue(msg('a')), /disk full/);
    assert.equal(outbox.getSnapshot().length, 0);
  });

  it('survives a damaged file at startup and keeps a copy for debugging', async () => {
    storage.data.set('outbox:v1', '{"v":1,"items":[{"id":42}]}');
    const outbox = make();
    await outbox.load();
    assert.equal(outbox.getSnapshot().length, 0);
    assert.ok(storage.data.has('outbox:v1:corrupt'));
    await outbox.enqueue(msg('a')); // and it works normally afterwards
    assert.equal(outbox.getSnapshot().length, 1);
  });

  it('joins a flush that is already running and sends what was queued meanwhile', async () => {
    const gate = deferred();
    behaviour = async (item) => {
      if (item.id === 'a') await gate.promise;
    };
    const outbox = make();
    await outbox.enqueue(msg('a'));
    const first = outbox.flush();
    await outbox.enqueue(msg('b'));
    const second = outbox.flush();
    assert.equal(first, second); // one run, not two at once
    gate.resolve();
    const summary = await first;
    assert.deepEqual(sent, ['a', 'b']); // each exactly once, in order
    assert.equal(summary.sent, 2);
  });

  it('never sends the same item twice, even when flush is called from many places', async () => {
    const calls: string[] = [];
    behaviour = async (item) => void calls.push(item.id);
    const outbox = make();
    await outbox.enqueue(msg('a'));
    await Promise.all([outbox.flush(), outbox.flush(), outbox.flush()]);
    assert.deepEqual(calls, ['a']);
  });

  it('treats an unexpected bug in send() as a failure of that item, not an endless loop', async () => {
    behaviour = async () => {
      throw new TypeError("undefined is not an object (evaluating 'x.y')");
    };
    const outbox = make();
    await outbox.enqueue(msg('a'));
    await outbox.flush();
    assert.equal(outbox.getSnapshot()[0].status, 'failed');
  });

  it('gives React a stable snapshot until something changes', async () => {
    const outbox = make();
    let notified = 0;
    const unsubscribe = outbox.subscribe(() => void notified++);
    const before = outbox.getSnapshot();
    assert.equal(outbox.getSnapshot(), before);
    await outbox.enqueue(msg('a'));
    assert.notEqual(outbox.getSnapshot(), before);
    assert.ok(notified >= 1);
    unsubscribe();
  });

  it('clear() removes everything, including the saved file (sign-out)', async () => {
    const outbox = make();
    await outbox.enqueue(msg('a'));
    await outbox.clear();
    assert.equal(outbox.getSnapshot().length, 0);
    assert.equal(storage.data.has('outbox:v1'), false);
  });
});
