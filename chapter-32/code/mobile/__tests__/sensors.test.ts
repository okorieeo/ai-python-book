import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { LowPassFilter, ShakeDetector, magnitude } from '../lib/cv/sensors';
import { nextPollDelay } from '../hooks/pollDelay';

const rest = { x: 0, y: 0, z: 1 }; // gravity only
const hard = { x: 2.2, y: 0.3, z: 0.4 }; // a violent movement

/** Feed readings 50 ms apart and report the times a shake was recognised. */
function shakes(readings: Array<{ x: number; y: number; z: number }>, detector = new ShakeDetector(), stepMs = 50): number[] {
  return readings.flatMap((r, i) => (detector.push(r, i * stepMs) ? [i * stepMs] : []));
}

describe('magnitude', () => {
  it('reads about 1 g for a phone lying still, in any orientation', () => {
    assert.equal(magnitude(rest), 1);
    assert.ok(Math.abs(magnitude({ x: 0, y: 1, z: 0 }) - 1) < 1e-9);
    assert.ok(Math.abs(magnitude({ x: 0.6, y: 0.8, z: 0 }) - 1) < 1e-9);
  });
});

describe('ShakeDetector', () => {
  it('does not fire for a phone at rest or one that is slowly tilted', () => {
    const tilting = Array.from({ length: 60 }, (_, i) => ({ x: Math.sin(i / 10), y: 0, z: Math.cos(i / 10) })); // always 1 g
    assert.deepEqual(shakes([...Array(40).fill(rest), ...tilting]), []);
  });

  it('does not fire for a single bump', () => {
    assert.deepEqual(shakes([rest, rest, hard, hard, hard, rest, rest, rest]), []);
  });

  it('fires on several hard movements close together', () => {
    const wiggle = [hard, rest, hard, rest, hard, rest];
    assert.deepEqual(shakes(wiggle), [200]); // the third movement completes the shake
  });

  it('counts a movement once, however many readings it spans', () => {
    assert.deepEqual(shakes([hard, hard, hard, hard, hard, hard, rest]), []);
  });

  it('ignores movements that are too far apart', () => {
    const slowWiggle = [hard, ...Array(20).fill(rest), hard, ...Array(20).fill(rest), hard, rest];
    assert.deepEqual(shakes(slowWiggle), []);
  });

  it('waits out a cooldown before firing again', () => {
    const burst = [hard, rest, hard, rest, hard, rest];
    const twice = shakes([...burst, ...burst]); // the second burst starts 300 ms after the first fired
    assert.equal(twice.length, 1);
    const later = shakes([...burst, ...Array(40).fill(rest), ...burst]);
    assert.equal(later.length, 2);
  });
});

describe('LowPassFilter', () => {
  it('starts at the first reading and moves a fraction of the way each time', () => {
    const f = new LowPassFilter(0.5);
    assert.equal(f.next(10), 10);
    assert.equal(f.next(20), 15);
    assert.equal(f.next(20), 17.5);
  });
  it('flattens a noisy signal', () => {
    const f = new LowPassFilter(0.1);
    const noisy = Array.from({ length: 200 }, (_, i) => 1 + (i % 2 === 0 ? 0.5 : -0.5));
    const out = noisy.map((v) => f.next(v));
    const spread = Math.max(...out.slice(100)) - Math.min(...out.slice(100));
    assert.ok(spread < 0.15, `spread ${spread}`);
  });
  it('refuses a nonsense alpha', () => {
    assert.throws(() => new LowPassFilter(0));
    assert.throws(() => new LowPassFilter(1.5));
  });
});

describe('nextPollDelay', () => {
  it('waits longer each time, up to five seconds', () => {
    assert.deepEqual([0, 1, 2, 3, 8, 20].map(nextPollDelay), [1000, 1500, 2000, 2500, 5000, 5000]);
  });
});
