"use client";

import { useQuery } from "@tanstack/react-query";
import { DayColumn } from "@/components/calendar/DayColumn";
import { getJson } from "@/lib/api";

type Occurrence = { event_id: string; title: string; start: string; end: string; recurring: boolean };

// The browser's own idea of today. The SERVER does all the time-zone work; we only pick the date.
const localToday = () => new Date().toLocaleDateString("en-CA"); // en-CA prints YYYY-MM-DD

export default function TodayPage() {
  const day = localToday();
  const { data, isPending, error } = useQuery({
    queryKey: ["events", day],
    queryFn: () => getJson<{ results: Occurrence[] }>(`/events/?start=${day}&end=${day}`),
  });
  if (isPending) return <p>Loading…</p>;
  if (error) return <p role="alert">Could not load your calendar.</p>;
  return <DayColumn day={day} events={data.results.map((o) => ({ id: o.event_id, title: o.title, start: o.start, end: o.end }))} />;
}
