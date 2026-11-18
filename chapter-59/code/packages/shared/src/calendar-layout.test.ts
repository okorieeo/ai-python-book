import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { layoutDay, minutesOnDay, type CalendarEvent } from "./calendar-layout.ts";

const DAY = "2026-11-12";
const ev = (id: string, start: string, end: string): CalendarEvent => ({ id, title: id, start: `${DAY}T${start}`, end: `${DAY}T${end}` });
const byId = (events: CalendarEvent[]) => Object.fromEntries(layoutDay(events, DAY).map((p) => [p.id, p]));

describe("minutesOnDay", () => {
  it("counts minutes after midnight", () => assert.equal(minutesOnDay("2026-11-12T15:30", DAY), 930));
  it("clips earlier and later days", () => {
    assert.equal(minutesOnDay("2026-11-11T23:00", DAY), 0);
    assert.equal(minutesOnDay("2026-11-13T01:00", DAY), 1440);
  });
  it("rejects anything that is not a local time", () => {
    assert.throws(() => minutesOnDay("tomorrow", DAY));
  });
});

describe("layoutDay", () => {
  it("a lone event takes the full width", () => {
    const p = byId([ev("a", "09:00", "10:00")])["a"]!;
    assert.deepEqual([p.column, p.columns], [0, 1]);
    assert.equal(p.top, 540 / 1440);
    assert.equal(p.height, 60 / 1440);
  });

  it("events that only touch do not share a row", () => {
    const l = byId([ev("a", "10:00", "11:00"), ev("b", "11:00", "12:00")]);
    assert.deepEqual([l["a"]!.columns, l["b"]!.columns], [1, 1]);
  });

  it("two overlapping events sit side by side", () => {
    const l = byId([ev("a", "10:00", "11:30"), ev("b", "11:00", "12:00")]);
    assert.deepEqual([l["a"]!.column, l["b"]!.column, l["a"]!.columns], [0, 1, 2]);
  });

  it("a freed lane is reused, and the cluster is as wide as its busiest moment", () => {
    // a: 10-12, b: 10-10:30, c: 10:30-11. c can reuse b's lane, so the cluster needs only 2 lanes.
    const l = byId([ev("a", "10:00", "12:00"), ev("b", "10:00", "10:30"), ev("c", "10:30", "11:00")]);
    assert.equal(l["a"]!.columns, 2);
    assert.equal(l["b"]!.column, l["c"]!.column);
  });

  it("separate clusters do not affect each other's width", () => {
    const l = byId([ev("a", "09:00", "10:00"), ev("b", "09:00", "10:00"), ev("c", "14:00", "15:00")]);
    assert.deepEqual([l["a"]!.columns, l["c"]!.columns], [2, 1]);
  });

  it("three at once need three lanes", () => {
    const l = byId([ev("a", "10:00", "11:00"), ev("b", "10:00", "11:00"), ev("c", "10:00", "11:00")]);
    assert.deepEqual(Object.values(l).map((p) => p.column).sort(), [0, 1, 2]);
    assert.ok(Object.values(l).every((p) => p.columns === 3));
  });

  it("tiny events stay tappable", () => {
    assert.equal(byId([ev("a", "09:00", "09:05")])["a"]!.height, 20 / 1440);
  });

  it("an event from the night before is clipped to midnight", () => {
    const e: CalendarEvent = { id: "n", title: "n", start: "2026-11-11T23:00", end: `${DAY}T01:00` };
    const p = layoutDay([e], DAY)[0]!;
    assert.deepEqual([p.top, p.height], [0, 60 / 1440]);
  });

  it("events on other days are left out", () => {
    const other: CalendarEvent = { id: "x", title: "x", start: "2026-11-13T09:00", end: "2026-11-13T10:00" };
    assert.deepEqual(layoutDay([other], DAY), []);
  });

  it("is deterministic regardless of input order", () => {
    const events = [ev("b", "10:00", "11:00"), ev("a", "10:00", "11:00"), ev("c", "10:30", "12:00")];
    assert.deepEqual(layoutDay(events, DAY), layoutDay([...events].reverse(), DAY));
  });
});
