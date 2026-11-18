import { describe, expect, it } from "vitest";
import { createDeltaBatcher } from "./delta-batcher";

function setup() {
  const emitted: [string, string][] = [];
  const frames = new Map<number, () => void>();
  let next = 1;
  const batcher = createDeltaBatcher(
    (id, text) => emitted.push([id, text]),
    (run) => { frames.set(next, run); return next++; },
    (h) => { frames.delete(h as number); },
  );
  const frame = () => { const all = [...frames.values()]; frames.clear(); all.forEach((f) => f()); };
  return { batcher, emitted, frame, scheduled: () => frames.size };
}

describe("createDeltaBatcher", () => {
  it("merges deltas from one frame into one update", () => {
    const { batcher, emitted, frame } = setup();
    batcher.push("a", "Hel"); batcher.push("a", "lo"); batcher.push("a", "!");
    expect(emitted).toEqual([]);
    frame();
    expect(emitted).toEqual([["a", "Hello!"]]);
  });

  it("asks for only one animation frame however many deltas arrive", () => {
    const { batcher, scheduled } = setup();
    for (let i = 0; i < 50; i++) batcher.push("a", "x");
    expect(scheduled()).toBe(1);
  });

  it("keeps the order across different messages", () => {
    const { batcher, emitted, frame } = setup();
    batcher.push("a", "1"); batcher.push("b", "2"); batcher.push("a", "3");
    frame();
    expect(emitted).toEqual([["a", "1"], ["b", "2"], ["a", "3"]]);
  });

  it("flush() delivers immediately and cancels the pending frame", () => {
    const { batcher, emitted, scheduled } = setup();
    batcher.push("a", "x");
    batcher.flush();
    expect(emitted).toEqual([["a", "x"]]);
    expect(scheduled()).toBe(0);
  });

  it("schedules again for deltas that arrive after a frame", () => {
    const { batcher, emitted, frame } = setup();
    batcher.push("a", "1"); frame();
    batcher.push("a", "2"); frame();
    expect(emitted).toEqual([["a", "1"], ["a", "2"]]);
  });

  it("cancel() drops pending text", () => {
    const { batcher, emitted, frame } = setup();
    batcher.push("a", "x");
    batcher.cancel();
    frame();
    expect(emitted).toEqual([]);
  });

  it("flush() with nothing pending does nothing", () => {
    const { batcher, emitted } = setup();
    batcher.flush();
    expect(emitted).toEqual([]);
  });
});
