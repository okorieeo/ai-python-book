"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  ResponsiveContainer,
  XAxis,
  YAxis,
} from "recharts";

import type { StatusCount } from "@/lib/types";

// Status colours carry meaning, so the value is printed on every bar as well.
const COLORS: Record<string, string> = {
  uploaded: "#6b7280",
  processing: "#d97706",
  ready: "#059669",
  failed: "#b3261e",
};

export function StatusChart({ counts }: { counts: StatusCount[] }) {
  return (
    <ResponsiveContainer width="100%" height={288}>
      <BarChart
        data={counts}
        margin={{ top: 20, right: 8, left: 0, bottom: 0 }}
      >
        <CartesianGrid
          strokeDasharray="3 3"
          vertical={false}
          stroke="#9ca3af55"
        />
        <XAxis dataKey="status" tick={{ fontSize: 12, fill: "#6b7280" }} />
        <YAxis
          allowDecimals={false}
          width={32}
          tick={{ fontSize: 12, fill: "#6b7280" }}
        />
        <Bar dataKey="count" name="Documents" radius={[4, 4, 0, 0]}>
          {counts.map((c) => (
            <Cell key={c.status} fill={COLORS[c.status] ?? "#2563eb"} />
          ))}
          <LabelList dataKey="count" position="top" fontSize={12} />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
