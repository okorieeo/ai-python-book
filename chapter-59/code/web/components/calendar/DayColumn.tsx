import { layoutDay, type CalendarEvent } from "@app/shared/calendar-layout";

const HOUR_PX = 48;

export function DayColumn({ day, events }: { day: string; events: CalendarEvent[] }) {
  const placed = layoutDay(events, day);
  return (
    <div className="relative border-l" style={{ height: 24 * HOUR_PX }} role="list" aria-label={`Events on ${day}`}>
      {Array.from({ length: 24 }, (_, h) => (
        <div key={h} className="absolute inset-x-0 border-t border-gray-100 dark:border-gray-800" style={{ top: h * HOUR_PX }} aria-hidden="true" />
      ))}
      {placed.map((p) => (
        <div key={`${p.id}-${p.start}`} role="listitem" title={`${p.title}, ${p.start.slice(11)} to ${p.end.slice(11)}`}
          className="absolute overflow-hidden rounded bg-blue-100 px-1 text-xs text-blue-900 dark:bg-blue-900 dark:text-blue-100"
          style={{ top: `${p.top * 100}%`, height: `${p.height * 100}%`, left: `${(p.column / p.columns) * 100}%`, width: `${100 / p.columns}%` }}>
          {p.title}
        </div>
      ))}
    </div>
  );
}
