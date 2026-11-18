// app/billing/page.tsx: shows the plan, offers upgrades and opens the customer portal. Not executed here.
"use client";

import { useEffect, useState } from "react";
import { BillingStatus, PlanKey, getStatus, openPortal, startCheckout } from "@/lib/billing";

const PLANS: { key: PlanKey; name: string; note: string }[] = [
  { key: "pro_monthly", name: "Pro, monthly", note: "14-day free trial" },
  { key: "pro_yearly", name: "Pro, yearly", note: "two months free" },
  { key: "team_monthly", name: "Team", note: "shared workspace and SSO" },
];

export default function BillingPage() {
  const [status, setStatus] = useState<BillingStatus | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { getStatus().then(setStatus).catch(() => setError("Could not load your plan.")); }, []);

  async function run(label: string, action: () => Promise<void>) {
    setBusy(label); setError(null);
    try { await action(); }                       // on success the browser leaves for Stripe
    catch (e) { setError(e instanceof Error ? e.message : "Something went wrong."); setBusy(null); }
  }

  if (!status) return <p>{error ?? "Loading…"}</p>;
  const until = status.until ? new Date(status.until * 1000).toLocaleDateString() : null;

  return (
    <main>
      <h1>Billing</h1>
      <p>
        Your plan: <strong>{status.tier}</strong> ({status.reason}{until ? `, until ${until}` : ""})
      </p>
      {status.status === "past_due" && <p role="alert">Your last payment failed. Update your card in the portal.</p>}

      {status.paid ? (
        <button disabled={busy !== null} onClick={() => run("portal", openPortal)}>
          {busy === "portal" ? "Opening…" : "Manage subscription"}
        </button>
      ) : (
        PLANS.map((p) => (
          <button key={p.key} disabled={busy !== null} onClick={() => run(p.key, () => startCheckout(p.key))}>
            {busy === p.key ? "Redirecting…" : `${p.name}: ${p.note}`}
          </button>
        ))
      )}
      {error && <p role="alert">{error}</p>}
    </main>
  );
}
