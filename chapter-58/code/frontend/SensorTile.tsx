import { Sparkline } from "./Sparkline";
import type { SensorInfo } from "./types";

type Status = "ok" | "high" | "low" | "stale" | "waiting";

function statusOf(s: SensorInfo, last: { ts: number; value: number } | undefined, now: number): Status {
  if (!last) return "waiting";
  if (now - last.ts > s.interval_s * 3 * 1000) return "stale";           // no reading for three intervals: do not show an old number as if it were live
  if (s.high_limit !== null && last.value > s.high_limit) return "high";
  if (s.low_limit !== null && last.value < s.low_limit) return "low";
  return "ok";
}

const COLORS: Record<Status, string> = { ok: "text-green-700", high: "text-red-700", low: "text-blue-700", stale: "text-gray-400", waiting: "text-gray-400" };
const LABELS: Record<Status, string> = { ok: "Normal", high: "Too high", low: "Too low", stale: "No recent data", waiting: "Waiting for data" };

export function SensorTile({ sensor, points, now }: { sensor: SensorInfo; points: { ts: number; value: number }[]; now: number }) {
  const last = points[points.length - 1];
  const status = statusOf(sensor, last, now);
  return (
    <section className="rounded-lg border p-4" aria-label={sensor.name}>
      <h3 className="text-sm text-gray-600">{sensor.name}</h3>
      <p className={`text-3xl font-semibold ${COLORS[status]}`}>
        {last ? last.value.toFixed(1) : "-"} <span className="text-base">{sensor.unit}</span>
      </p>
      {/* colour is never the only signal: the status is also written in words */}
      <p className={`text-sm ${COLORS[status]}`}>{LABELS[status]}</p>
      <div className={COLORS[status]}><Sparkline points={points.map((p) => p.value)} /></div>
    </section>
  );
}
