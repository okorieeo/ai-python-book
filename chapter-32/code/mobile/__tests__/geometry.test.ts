import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { StableDetector, clampBox, iou, mapBoxToView, nms, orderCorners, type Detection } from '../lib/cv/geometry';

const det = (x: number, y: number, w: number, h: number, score: number, label = 'cup'): Detection => ({ box: { x, y, width: w, height: h }, score, label });

describe('iou', () => {
  it('is 1 for identical boxes, 0 for boxes that do not touch, and exact in between', () => {
    const a = { x: 0, y: 0, width: 10, height: 10 };
    assert.equal(iou(a, a), 1);
    assert.equal(iou(a, { x: 20, y: 20, width: 5, height: 5 }), 0);
    assert.equal(iou(a, { x: 10, y: 0, width: 10, height: 10 }), 0); // touching edges only
    assert.equal(iou(a, { x: 5, y: 0, width: 10, height: 10 }), 50 / 150); // overlap 50, union 150
  });
  it('is symmetric and copes with a box inside another', () => {
    const big = { x: 0, y: 0, width: 10, height: 10 };
    const small = { x: 2, y: 2, width: 5, height: 5 };
    assert.equal(iou(big, small), iou(small, big));
    assert.equal(iou(big, small), 25 / 100);
  });
});

describe('nms', () => {
  it('keeps the best of several boxes on the same object', () => {
    const result = nms([det(10, 10, 100, 100, 0.8), det(12, 11, 100, 100, 0.95), det(8, 9, 102, 100, 0.6)]);
    assert.deepEqual(result.map((d) => d.score), [0.95]);
  });
  it('keeps separate objects, and boxes with different labels do not suppress each other', () => {
    const result = nms([det(0, 0, 100, 100, 0.9), det(300, 300, 100, 100, 0.8), det(5, 5, 100, 100, 0.7, 'table')]);
    assert.deepEqual(result.map((d) => [d.label, d.score]), [['cup', 0.9], ['cup', 0.8], ['table', 0.7]]);
  });
  it('drops weak detections and caps the count', () => {
    assert.deepEqual(nms([det(0, 0, 10, 10, 0.2)]), []);
    const many = Array.from({ length: 30 }, (_, i) => det(i * 200, 0, 50, 50, 0.9 - i * 0.01));
    assert.equal(nms(many, { maxDetections: 5 }).length, 5);
  });
});

describe('mapBoxToView', () => {
  const portraitFrame = { width: 1000, height: 2000 };
  const square = { width: 400, height: 400 };
  it('"cover" crops the frame: the same box lands off-centre', () => {
    const box = { x: 0, y: 0, width: 1000, height: 1000 };
    assert.deepEqual(mapBoxToView(box, portraitFrame, square, 'cover'), { x: 0, y: -200, width: 400, height: 400 });
  });
  it('"contain" shows the whole frame with bars at the sides', () => {
    const box = { x: 0, y: 0, width: 1000, height: 1000 };
    assert.deepEqual(mapBoxToView(box, portraitFrame, square, 'contain'), { x: 100, y: 0, width: 200, height: 200 });
  });
  it('mirrors a selfie camera', () => {
    const box = { x: 0, y: 0, width: 100, height: 100 };
    const view = { width: 400, height: 800 };
    const frame = { width: 400, height: 800 };
    assert.deepEqual(mapBoxToView(box, frame, view, 'cover', true), { x: 300, y: 0, width: 100, height: 100 });
  });
  it('a frame with the same shape as the view only scales', () => {
    assert.deepEqual(mapBoxToView({ x: 10, y: 20, width: 30, height: 40 }, { width: 100, height: 200 }, { width: 200, height: 400 }, 'cover'), { x: 20, y: 40, width: 60, height: 80 });
  });
});

describe('clampBox', () => {
  it('cuts to the screen and returns null when nothing is visible', () => {
    const view = { width: 100, height: 100 };
    assert.deepEqual(clampBox({ x: -20, y: 50, width: 60, height: 100 }, view), { x: 0, y: 50, width: 40, height: 50 });
    assert.equal(clampBox({ x: 120, y: 0, width: 10, height: 10 }, view), null);
  });
});

describe('orderCorners', () => {
  const tl = { x: 0, y: 0 }, tr = { x: 10, y: 0 }, br = { x: 10, y: 10 }, bl = { x: 0, y: 10 };
  it('returns the same order everywhere (top-left, top-right, bottom-right, bottom-left)', () => {
    assert.deepEqual(orderCorners([tl, tr, br, bl], 'android'), [tl, tr, br, bl]);
    assert.deepEqual(orderCorners([tl, tr, br, bl], 'web'), [tl, tr, br, bl]);
    assert.deepEqual(orderCorners([bl, br, tl, tr], 'ios'), [tl, tr, br, bl]); // iOS: bottom-left, bottom-right, top-left, top-right
  });
  it('leaves an unavailable result (no corners) alone', () => {
    assert.deepEqual(orderCorners([], 'ios'), []);
  });
});

describe('StableDetector', () => {
  it('acts only after the same value is seen in enough frames in a row', () => {
    const d = new StableDetector({ framesRequired: 3 });
    assert.equal(d.update('A', 0), null);
    assert.equal(d.update('A', 30), null);
    assert.equal(d.update('A', 60), 'A');
  });
  it('a flicker resets the count', () => {
    const d = new StableDetector({ framesRequired: 3 });
    d.update('A', 0); d.update('A', 30);
    assert.equal(d.update('B', 60), null);
    assert.equal(d.update('A', 90), null);
    assert.equal(d.update(null, 120), null);
    assert.equal(d.update('A', 150), null);
  });
  it('does not fire again for the same code while it stays in view, until the cooldown passes', () => {
    const d = new StableDetector({ framesRequired: 2, cooldownMs: 1000 });
    d.update('A', 0);
    assert.equal(d.update('A', 30), 'A');
    for (let t = 60; t < 900; t += 30) assert.equal(d.update('A', t), null);
    assert.equal(d.update('A', 1100), 'A');
  });
  it('allows the same code again once it has left the view', () => {
    const d = new StableDetector({ framesRequired: 2, cooldownMs: 60_000, clearAfterEmptyFrames: 3 });
    d.update('A', 0);
    assert.equal(d.update('A', 30), 'A');
    d.update(null, 60); d.update(null, 90); d.update(null, 120);
    d.update('A', 150);
    assert.equal(d.update('A', 180), 'A');
  });
  it('a different code fires at once, cooldown or not', () => {
    const d = new StableDetector({ framesRequired: 2, cooldownMs: 60_000 });
    d.update('A', 0); assert.equal(d.update('A', 30), 'A');
    d.update('B', 60);
    assert.equal(d.update('B', 90), 'B');
  });
});
