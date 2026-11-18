import type { InsightResponse } from "./types";

export function InsightCard({ insight }: { insight: InsightResponse }) {
  const factText = Object.fromEntries(insight.facts.map((f) => [f.id, f.text]));
  return (
    <section className="rounded-lg border p-4">
      <h2 className="font-semibold">{insight.ai_generated ? "AI suggestions" : "Key facts"}</h2>
      <p className="mt-1">{insight.summary}</p>
      <ul className="mt-3 space-y-3">
        {insight.recommendations.map((r, i) => (
          <li key={i} className="rounded bg-gray-50 p-3">
            <p className="font-medium">{r.title} <span className="text-xs uppercase text-gray-500">{r.urgency.replace("_", " ")}, confidence {r.confidence}</span></p>
            <p>{r.action}</p>
            <p className="text-sm text-gray-600">{r.reason}</p>
            {r.redacted && <p className="text-sm text-amber-700">Specific advice was removed for safety: ask a professional.</p>}
            {/* the evidence is one click away: each chip shows the exact fact computed from your sensors */}
            <p className="mt-1 flex flex-wrap gap-1">
              {r.fact_ids.map((id) => <span key={id} title={factText[id]} className="rounded-full border px-2 text-xs">{id}</span>)}
            </p>
          </li>
        ))}
      </ul>
      <p className="mt-3 text-xs text-gray-500">{insight.notice}</p>
    </section>
  );
}
