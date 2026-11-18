"use client";
import { useEffect, useState } from "react";
import { getUsage } from "./api";
import type { UsageSnapshot } from "./types";

function Bar({ label, used, limit }: { label: string; used: number; limit: number }) {
  const pct = Math.min(100, Math.round((used / limit) * 100));
  return (
    <div>
      <div className="flex justify-between text-sm"><span>{label}</span><span>{used} / {limit}</span></div>
      <div className="h-2 rounded bg-gray-200" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
        <div className={`h-2 rounded ${pct >= 90 ? "bg-red-500" : "bg-blue-500"}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

export function UsageMeter({ refreshKey }: { refreshKey?: number }) {
  const [u, setU] = useState<UsageSnapshot | null>(null);
  useEffect(() => { getUsage().then(setU).catch(() => setU(null)); }, [refreshKey]);
  if (!u) return null;
  return (
    <div className="space-y-2">
      <Bar label="Questions this month" used={u.questions.used} limit={u.questions.limit} />
      <Bar label="Pages this month" used={u.pages.used} limit={u.pages.limit} />
      <p className="text-xs text-gray-500">Plan: {u.plan}. Resets {new Date(u.resets_at).toLocaleDateString()}.</p>
    </div>
  );
}
