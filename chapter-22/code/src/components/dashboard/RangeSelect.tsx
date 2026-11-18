import { ui } from "@/lib/ui";

const RANGES = [7, 30, 90];

export function RangeSelect({
  value,
  onChange,
}: {
  value: number;
  onChange: (days: number) => void;
}) {
  return (
    <div
      role="group"
      aria-label="Date range"
      className={`${ui.field} inline-flex overflow-hidden p-0`}
    >
      {RANGES.map((days) => (
        <button
          key={days}
          aria-pressed={value === days}
          onClick={() => onChange(days)}
          className={`px-3 py-1 ${
            value === days
              ? "bg-blue-600 text-white"
              : "hover:bg-gray-50 dark:hover:bg-gray-800"
          }`}
        >
          {days} days
        </button>
      ))}
    </div>
  );
}
