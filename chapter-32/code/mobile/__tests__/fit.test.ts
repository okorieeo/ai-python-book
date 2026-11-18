import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { fitWithin } from '../lib/media/fit';

describe('fitWithin', () => {
  it('shrinks a camera photo to the long-side limit and keeps its shape', () => {
    assert.deepEqual(fitWithin(4032, 3024, 1568), { width: 1568, height: 1176 });
    assert.deepEqual(fitWithin(3024, 4032, 1568), { width: 1176, height: 1568 });
  });

  it('never enlarges a picture that already fits', () => {
    assert.deepEqual(fitWithin(800, 600, 1568), { width: 800, height: 600 });
    assert.deepEqual(fitWithin(1568, 1568, 1568), { width: 1568, height: 1568 });
  });

  it('never produces a side of zero pixels', () => {
    assert.deepEqual(fitWithin(10000, 2, 1568), { width: 1568, height: 1 });
  });

  it('refuses nonsense sizes', () => {
    assert.throws(() => fitWithin(0, 100, 1568));
  });
});
