import { formatNumber } from "@/lib/format";
import { ui } from "@/lib/ui";

export function StatCard({
  label,
  value,
  hint,
}: {
  label: string;
  value: number | undefined; // undefined means "still loading"
  hint?: string;
}) {
  return (
    <div className={ui.card}>
      <p className="text-sm text-gray-500">{label}</p>
      {value === undefined ? (
        <div
          role="status"
          aria-label={`Loading ${label}`}
          className={`${ui.skeleton} mt-2 h-8 w-24`}
        />
      ) : (
        <p className="mt-1 text-3xl font-semibold tabular-nums">
          {formatNumber(value)}
        </p>
      )}
      {hint && <p className="mt-1 text-xs text-gray-400">{hint}</p>}
    </div>
  );
}
