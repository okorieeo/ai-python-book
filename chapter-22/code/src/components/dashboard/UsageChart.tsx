"use client";

import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { formatCompact, formatDay, formatNumber } from "@/lib/format";
import type { UsagePoint } from "@/lib/types";

export function UsageChart({ points }: { points: UsagePoint[] }) {
  return (
    <ResponsiveContainer width="100%" height={288}>
      <AreaChart
        data={points}
        margin={{ top: 4, right: 8, left: 0, bottom: 0 }}
      >
        <CartesianGrid
          strokeDasharray="3 3"
          vertical={false}
          stroke="#9ca3af55"
        />
        <XAxis
          dataKey="date"
          tickFormatter={formatDay}
          minTickGap={24}
          tick={{ fontSize: 12, fill: "#6b7280" }}
        />
        <YAxis
          tickFormatter={formatCompact}
          width={48}
          tick={{ fontSize: 12, fill: "#6b7280" }}
        />
        <Tooltip
          labelFormatter={(label) => formatDay(String(label))}
          formatter={(value) => formatNumber(Number(value))}
        />
        <Legend />
        {/* Different fills AND strokes: colour alone does not tell them apart */}
        <Area
          type="monotone"
          dataKey="input_tokens"
          name="Input tokens"
          stackId="t"
          stroke="#2563eb"
          fill="#2563eb"
          fillOpacity={0.35}
        />
        <Area
          type="monotone"
          dataKey="output_tokens"
          name="Output tokens"
          stackId="t"
          stroke="#7c3aed"
          fill="#7c3aed"
          fillOpacity={0.2}
          strokeDasharray="5 3"
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}
