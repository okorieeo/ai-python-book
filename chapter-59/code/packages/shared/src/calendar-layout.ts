// Pure layout maths for a day column. The server sends LOCAL time strings ("2026-11-12T15:00"),
// so nothing here ever touches Date or time zones: it is just string and number work.

export type CalendarEvent = { id: string; title: string; start: string; end: string };
export type Positioned = CalendarEvent & {
  top: number;      // 0..1, fraction of the day
  height: number;   // 0..1
  column: number;   // 0-based lane within its cluster of overlapping events
  columns: number;  // how many lanes that cluster needs
};

export const MINUTES_PER_DAY = 1440;
export const MIN_VISIBLE_MINUTES = 20; // a 5-minute event must still be tappable

const LOCAL = /^(\d{4}-\d{2}-\d{2})T(\d{2}):(\d{2})/;

/** Minutes after midnight of `day` ("2026-11-12") for a local timestamp, clipped to 0..1440. */
export function minutesOnDay(local: string, day: string): number {
  const match = LOCAL.exec(local);
  if (!match) throw new Error(`Not a local time: ${local}`);
  const [, date, hh, mm] = match;
  if (date! < day) return 0;
  if (date! > day) return MINUTES_PER_DAY;
  return Number(hh) * 60 + Number(mm);
}

type Span = { event: CalendarEvent; start: number; end: number };

/** Place events side by side when they overlap. Events that only touch (10:00-11:00 and 11:00-12:00) do not overlap. */
export function layoutDay(events: CalendarEvent[], day: string): Positioned[] {
  const spans: Span[] = events
    .map((event) => {
      const start = minutesOnDay(event.start, day);
      const end = Math.max(minutesOnDay(event.end, day), start + MIN_VISIBLE_MINUTES);
      return { event, start, end: Math.min(end, MINUTES_PER_DAY) };
    })
    .filter((s) => s.start < MINUTES_PER_DAY && minutesOnDay(s.event.end, day) > 0)
    .sort((a, b) => a.start - b.start || b.end - a.end || a.event.id.localeCompare(b.event.id));

  const out: Positioned[] = [];
  let cluster: { span: Span; column: number }[] = [];
  let laneEnds: number[] = [];
  let clusterEnd = -1;

  const flush = () => {
    for (const { span, column } of cluster) {
      out.push({
        ...span.event,
        top: span.start / MINUTES_PER_DAY,
        height: (span.end - span.start) / MINUTES_PER_DAY,
        column,
        columns: laneEnds.length,
      });
    }
    cluster = [];
    laneEnds = [];
    clusterEnd = -1;
  };

  for (const span of spans) {
    if (cluster.length > 0 && span.start >= clusterEnd) flush(); // nothing overlaps: start a new cluster
    let lane = laneEnds.findIndex((end) => end <= span.start);
    if (lane === -1) {
      lane = laneEnds.length;
      laneEnds.push(span.end);
    } else {
      laneEnds[lane] = span.end;
    }
    cluster.push({ span, column: lane });
    clusterEnd = Math.max(clusterEnd, span.end);
  }
  flush();
  return out;
}
