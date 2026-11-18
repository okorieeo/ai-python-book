"use client";
import { useState } from "react";
import type { AlertItem } from "./types";

const API = process.env.NEXT_PUBLIC_API_URL!;

export function AlertList({ alerts, onChanged, canAck }: { alerts: AlertItem[]; onChanged: () => void; canAck: boolean }) {
  const [error, setError] = useState<string | null>(null);

  async function ack(id: number) {
    setError(null);
    const csrf = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/)?.[1] ?? "";
    const res = await fetch(`${API}/api/alerts/${id}/ack/`, { method: "POST", credentials: "include", headers: { "X-CSRFToken": decodeURIComponent(csrf) } });
    if (res.ok) onChanged();
    else setError((await res.json().catch(() => ({}))).message ?? "Could not acknowledge this alert.");
  }

  return (
    <ul className="space-y-2">
      {error && <li role="alert" className="text-red-600">{error}</li>}
      {alerts.map((a) => (
        <li key={a.id} className={`rounded border-l-4 p-3 ${a.severity === "critical" ? "border-red-600" : "border-amber-500"}`}>
          <p className="font-medium">{a.severity === "critical" ? "Critical" : "Warning"}: {a.rule_name} <span className="text-gray-500">({a.site_name}, {a.sensor_name})</span></p>
          <p className="text-sm text-gray-600">
            Started {new Date(a.started_at).toLocaleString()}
            {a.resolved_at ? `, resolved ${new Date(a.resolved_at).toLocaleTimeString()}` : ", still active"}
            {a.peak_value !== null && `, value ${a.peak_value}`}
          </p>
          {!a.resolved_at && !a.acknowledged_at && canAck && <button onClick={() => ack(a.id)} className="mt-2 rounded border px-3 py-1">Acknowledge</button>}
          {a.acknowledged_at && <p className="text-sm text-green-700">Acknowledged</p>}
        </li>
      ))}
      {alerts.length === 0 && <li className="text-gray-500">No alerts. Everything is within limits.</li>}
    </ul>
  );
}
