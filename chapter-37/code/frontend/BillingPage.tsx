// app/billing/page.tsx: shows the plan, the price list for the customer's currency, and the controls. Not executed here.
"use client";

import { useEffect, useState } from "react";
import {
  BillingStatus, PlanKey, cancelSubscription, formatMoney, getStatus, pay, resumeSubscription, updateCard,
} from "@/lib/paystack";

// One price list per currency: a Paystack plan has a single currency, so we never convert on the fly.
const PRICE_LISTS: Record<"NGN" | "USD", { key: PlanKey; name: string; kobo: number }[]> = {
  NGN: [
    { key: "pro_monthly_ngn", name: "Pro, monthly", kobo: 500000 },
    { key: "pro_yearly_ngn", name: "Pro, yearly", kobo: 5000000 },
    { key: "team_monthly_ngn", name: "Team, monthly", kobo: 1500000 },
  ],
  USD: [{ key: "pro_monthly_usd", name: "Pro, monthly", kobo: 1000 }],
};

export default function BillingPage({ currency = "NGN" }: { currency?: "NGN" | "USD" }) {
  const [status, setStatus] = useState<BillingStatus | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { getStatus().then(setStatus).catch(() => setError("Could not load your plan.")); }, []);

  async function run(label: string, action: () => Promise<unknown>, refresh = false) {
    setBusy(label); setError(null);
    try { await action(); if (refresh) setStatus(await getStatus()); }
    catch (e) { setError(e instanceof Error ? e.message : "Something went wrong."); }
    finally { setBusy(null); }
  }

  if (!status) return <p>{error ?? "Loading…"}</p>;
  const until = status.until ? new Date(status.until * 1000).toLocaleDateString() : null;

  return (
    <main>
      <h1>Billing</h1>
      <p>Your plan: <strong>{status.tier}</strong> ({status.reason}{until ? `, until ${until}` : ""})</p>
      {status.reason.startsWith("last renewal failed") && (
        <p role="alert">Your last payment failed. <button onClick={() => run("card", updateCard)}>Update your card</button></p>
      )}
      {status.switching_to && <p>Your plan will change to {status.switching_to} at your next payment date.</p>}

      {!status.paid ? (
        PRICE_LISTS[currency].map((p) => (
          <button key={p.key} disabled={busy !== null} onClick={() => run(p.key, () => pay(p.key, "subscribe"))}>
            {busy === p.key ? "Redirecting…" : `${p.name}: ${formatMoney(p.kobo, currency)}`}
          </button>
        ))
      ) : status.reason.startsWith("cancelled") ? (
        <button disabled={busy !== null} onClick={() => run("resume", resumeSubscription, true)}>Resume subscription</button>
      ) : (
        <>
          <button disabled={busy !== null} onClick={() => run("cancel", cancelSubscription, true)}>Cancel at the end of the period</button>
          <button disabled={busy !== null} onClick={() => run("card", updateCard)}>Update card</button>
        </>
      )}
      {error && <p role="alert">{error}</p>}
    </main>
  );
}
