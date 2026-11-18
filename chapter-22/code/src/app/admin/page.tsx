"use client";

import { Suspense } from "react";

import { ChartCard } from "@/components/dashboard/ChartCard";
import { RangeSelect } from "@/components/dashboard/RangeSelect";
import { StatCard } from "@/components/dashboard/StatCard";
import { StatusChart } from "@/components/dashboard/StatusChart";
import { TopUsersList } from "@/components/dashboard/TopUsersList";
import { UsageChart } from "@/components/dashboard/UsageChart";
import { RequirePermission } from "@/components/RoleGate";
import {
  useDocumentStatus,
  useOverview,
  useTopUsers,
  useUsageSeries,
} from "@/hooks/useAdmin";
import { useUrlParams } from "@/hooks/useUrlParams";
import { formatDay } from "@/lib/format";

export default function OverviewPage() {
  return (
    <RequirePermission permission="view_analytics">
      <Suspense>
        <Overview />
      </Suspense>
    </RequirePermission>
  );
}

function chartState(
  q: { isPending: boolean; isError: boolean },
  empty: boolean,
) {
  if (q.isPending) return "loading" as const;
  if (q.isError) return "error" as const;
  return empty ? ("empty" as const) : ("ready" as const);
}

function Overview() {
  const { get, set } = useUrlParams();
  const requested = Number(get("days", "30"));
  // trust nothing in a URL: anything unexpected becomes 30
  const days = [7, 30, 90].includes(requested) ? requested : 30;

  const overview = useOverview();
  const usage = useUsageSeries(days);
  const top = useTopUsers(days);
  const docs = useDocumentStatus();
  const series = usage.data?.series ?? [];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold">Overview</h1>
        <RangeSelect value={days} onChange={(d) => set({ days: String(d) })} />
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Users"
          value={overview.data?.users_total}
          hint={
            overview.data
              ? `${overview.data.users_new_7d} joined this week`
              : undefined
          }
        />
        <StatCard label="Tokens today" value={overview.data?.tokens_today} />
        <StatCard
          label="Messages today"
          value={overview.data?.messages_today}
        />
        <StatCard label="Documents" value={overview.data?.documents_total} />
      </div>

      <ChartCard
        title="AI usage"
        description={`Tokens per day, last ${days} days`}
        state={chartState(
          usage,
          series.every((p) => p.calls === 0),
        )}
        onRetry={() => usage.refetch()}
        table={{
          caption: `Tokens per day, last ${days} days`,
          headers: ["Day", "Input tokens", "Output tokens"],
          rows: series.map((p) => [
            formatDay(p.date),
            p.input_tokens,
            p.output_tokens,
          ]),
        }}
      >
        <UsageChart points={series} />
      </ChartCard>

      <div className="grid gap-6 lg:grid-cols-2">
        <ChartCard
          title="Documents by status"
          state={chartState(docs, !docs.data?.some((d) => d.count > 0))}
          onRetry={() => docs.refetch()}
          table={{
            caption: "Documents by status",
            headers: ["Status", "Documents"],
            rows: (docs.data ?? []).map((d) => [d.status, d.count]),
          }}
        >
          <StatusChart counts={docs.data ?? []} />
        </ChartCard>
        <ChartCard
          title="Heaviest users"
          description={`Tokens, last ${days} days`}
          state={chartState(top, !top.data?.length)}
          onRetry={() => top.refetch()}
        >
          <TopUsersList users={top.data ?? []} />
        </ChartCard>
      </div>
    </div>
  );
}
