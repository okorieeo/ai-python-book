import assert from 'node:assert/strict';
import { beforeEach, describe, it } from 'node:test';
import { ReconnectingSocket, ReconnectPolicy, type SocketLike, type SocketStatus } from '../lib/net/reconnect';

class FakeSocket implements SocketLike {
  onopen: SocketLike['onopen'] = null;
  onclose: SocketLike['onclose'] = null;
  onerror: SocketLike['onerror'] = null;
  onmessage: SocketLike['onmessage'] = null;
  sent: string[] = [];
  closed = false;
  send(data: string) {
    this.sent.push(data);
  }
  close() {
    this.closed = true;
  }
  open() {
    this.onopen?.({});
  }
  drop() {
    this.onclose?.({});
  }
  receive(data: unknown) {
    this.onmessage?.({ data });
  }
}

/** A clock you advance by hand, so the test never really waits. */
function fakeTimers() {
  let nextId = 1;
  const pending = new Map<number, { fn: () => void; ms: number }>();
  return {
    pending,
    setTimeoutFn: (fn: () => void, ms: number) => {
      const id = nextId++;
      pending.set(id, { fn, ms });
      return id as unknown as ReturnType<typeof setTimeout>;
    },
    clearTimeoutFn: (id: ReturnType<typeof setTimeout>) => void pending.delete(id as unknown as number),
    /** Run the earliest pending timer and return how long it was set for. */
    fireNext(): number {
      const [id, timer] = [...pending.entries()][0] ?? [];
      assert.ok(id !== undefined && timer, 'expected a pending timer');
      pending.delete(id);
      timer.fn();
      return timer.ms;
    },
  };
}

describe('ReconnectPolicy', () => {
  it('hands out growing delays, then null when it is time to give up', () => {
    const policy = new ReconnectPolicy({ random: () => 0.5, maxAttempts: 3 });
    assert.deepEqual([policy.nextDelay(), policy.nextDelay(), policy.nextDelay(), policy.nextDelay()], [250, 500, 1000, null]);
    policy.reset();
    assert.equal(policy.nextDelay(), 250);
  });
});

describe('ReconnectingSocket', () => {
  let sockets: FakeSocket[];
  let timers: ReturnType<typeof fakeTimers>;
  let statuses: SocketStatus[];
  let received: unknown[];
  let socket: ReconnectingSocket;

  const make = (maxAttempts = 10) => {
    socket = new ReconnectingSocket({
      createSocket: () => {
        const s = new FakeSocket();
        sockets.push(s);
        return s;
      },
      onMessage: (data) => received.push(data),
      onStatus: (s) => statuses.push(s),
      policy: new ReconnectPolicy({ random: () => 0.5, maxAttempts }),
      stableAfterMs: 10_000,
      setTimeoutFn: timers.setTimeoutFn,
      clearTimeoutFn: timers.clearTimeoutFn,
    });
  };

  beforeEach(() => {
    sockets = [];
    statuses = [];
    received = [];
    timers = fakeTimers();
    make();
  });

  it('connects, passes messages along and sends only while open', () => {
    socket.start();
    assert.equal(socket.send('too early'), false);
    sockets[0].open();
    sockets[0].receive('hello');
    assert.equal(socket.send('hi'), true);
    assert.deepEqual(received, ['hello']);
    assert.deepEqual(sockets[0].sent, ['hi']);
    assert.deepEqual(statuses, ['connecting', 'open']);
  });

  it('reconnects after an unexpected drop, waiting longer each time it fails', () => {
    socket.start();
    sockets[0].drop();
    assert.equal(socket.status, 'reconnecting');
    assert.equal(timers.fireNext(), 250);
    sockets[1].drop();
    assert.equal(timers.fireNext(), 500);
    sockets[2].drop();
    assert.equal(timers.fireNext(), 1000);
    assert.equal(sockets.length, 4);
  });

  it('gives up after too many failures in a row', () => {
    make(2);
    socket.start();
    sockets[0].drop();
    timers.fireNext();
    sockets[1].drop();
    timers.fireNext();
    sockets[2].drop();
    assert.equal(socket.status, 'gave-up');
    assert.equal(timers.pending.size, 0);
  });

  it('forgets earlier failures only after the connection has stayed up for a while', () => {
    socket.start();
    sockets[0].drop();
    timers.fireNext(); // attempt 0
    sockets[1].open();
    timers.fireNext(); // the "stable for 10 s" timer: attempts reset
    sockets[1].drop();
    assert.equal(timers.fireNext(), 250); // starts from the beginning again

    sockets[2].open();
    sockets[2].drop(); // flapping: dropped before it counted as stable
    assert.equal(timers.fireNext(), 500); // the backoff kept growing
  });

  it('pauses while offline and reconnects at once when the network returns', () => {
    socket.start();
    sockets[0].open();
    socket.setOnline(false);
    assert.equal(socket.status, 'offline');
    assert.equal(sockets[0].closed, true);
    assert.equal(timers.pending.size, 0);

    socket.setOnline(true);
    assert.equal(sockets.length, 2); // no waiting for a timer
    assert.equal(socket.status, 'connecting');
  });

  it('ignores events from a socket it has already replaced', () => {
    socket.start();
    const old = sockets[0];
    socket.setOnline(false);
    socket.setOnline(true);
    old.receive('stale');
    old.drop();
    assert.deepEqual(received, []);
    assert.equal(sockets.length, 2);
    assert.equal(timers.pending.size, 0);
  });

  it('stop() ends it for good', () => {
    socket.start();
    sockets[0].open();
    socket.stop();
    assert.equal(socket.status, 'closed');
    sockets[0].drop();
    assert.equal(timers.pending.size, 0);
    assert.equal(sockets.length, 1);
  });
});
