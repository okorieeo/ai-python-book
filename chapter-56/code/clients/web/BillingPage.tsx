"use client";

import { useCallback, useEffect, useState } from "react";

type PlanRow = { code: string; name: string; daily_message_limit: number; price_usd_cents: number };
type SubscriptionInfo = { plan: PlanRow; status: string; gateway: string; current_period_end: string | null;
                          cancel_at_period_end: boolean; usage: { used: number; limit: number } };

export default function BillingPage({ apiBase, getAccessToken }: { apiBase: string; getAccessToken: () => Promise<string | null> }) {
  const [plans, setPlans] = useState<PlanRow[]>([]);
  const [sub, setSub] = useState<SubscriptionInfo | null>(null);
  const [gateway, setGateway] = useState<"stripe" | "paystack">("stripe");
  const [message, setMessage] = useState("");

  const call = useCallback(async (path: string, method = "GET", body?: unknown) => {
    const token = await getAccessToken();
    return fetch(`${apiBase}/billing/${path}`, { method, headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
                                                  body: body ? JSON.stringify(body) : undefined });
  }, [apiBase, getAccessToken]);

  const refresh = useCallback(async () => {
    const [p, s] = await Promise.all([call("plans/"), call("subscription/")]);
    if (p.ok) setPlans(await p.json());
    if (s.ok) setSub(await s.json());
    return s.ok ? ((await s.clone().json()) as SubscriptionInfo) : null;
  }, [call]);

  useEffect(() => {
    void refresh();
    // Coming back from the gateway: the webhook may arrive a few seconds AFTER the redirect, so poll briefly.
    if (new URLSearchParams(window.location.search).get("checkout") !== "success") return;
    setMessage("Confirming your payment…");
    let tries = 0;
    const timer = setInterval(async () => {
      const latest = await refresh();
      if (latest?.plan.code !== "free" || ++tries >= 15) {
        clearInterval(timer);
        setMessage(latest?.plan.code !== "free" ? "You are on Pro. Thank you!" : "Still waiting for the payment confirmation. This can take a minute.");
      }
    }, 2000);
    return () => clearInterval(timer);
  }, [refresh]);

  const upgrade = async (plan: string) => {
    const res = await call("checkout/", "POST", { plan, gateway });
    const data = await res.json();
    if (res.ok) window.location.assign(data.url as string); // the PRICE is decided by the server, never by this page
    else setMessage(data.detail ?? "Could not start checkout.");
  };

  const manage = async () => {
    const res = await call("portal/", "POST");
    const data = await res.json();
    if (res.ok) window.location.assign(data.url as string); else setMessage(data.detail ?? "Billing portal unavailable.");
  };

  return (
    <main className="mx-auto max-w-3xl space-y-6 p-6">
      <h1 className="text-2xl font-bold">Plans</h1>
      {message && <p role="status">{message}</p>}
      {sub && <p>You are on <strong>{sub.plan.name}</strong>. Used {sub.usage.used} of {sub.usage.limit} messages today.
        {sub.cancel_at_period_end && sub.current_period_end && ` Ends on ${new Date(sub.current_period_end).toLocaleDateString()}.`}</p>}
      <fieldset className="flex gap-4">
        <legend className="text-sm text-gray-600">Pay with</legend>
        {(["stripe", "paystack"] as const).map((g) => (
          <label key={g}><input type="radio" name="gateway" checked={gateway === g} onChange={() => setGateway(g)} /> {g === "stripe" ? "Card (Stripe)" : "Paystack"}</label>
        ))}
      </fieldset>
      <ul className="grid gap-4 sm:grid-cols-2">
        {plans.map((p) => (
          <li key={p.code} className="rounded border p-4">
            <h2 className="font-semibold">{p.name}</h2>
            <p>{p.price_usd_cents === 0 ? "Free" : `$${(p.price_usd_cents / 100).toFixed(2)} / month`}</p>
            <p className="text-sm text-gray-600">{p.daily_message_limit} messages per day</p>
            {p.code !== "free" && sub?.plan.code === "free" && (
              <button className="mt-3 rounded bg-blue-600 px-3 py-1 text-white" onClick={() => upgrade(p.code)}>Upgrade</button>)}
          </li>
        ))}
      </ul>
      {sub && sub.plan.code !== "free" && <button className="underline" onClick={manage}>Manage subscription</button>}
    </main>
  );
}
