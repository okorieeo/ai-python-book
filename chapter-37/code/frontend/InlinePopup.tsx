// components/PayInPopup.tsx: Paystack's popup, resumed from an access_code made by OUR server, so the amount
// cannot be changed in the browser. npm install @paystack/inline-js (check its README for the current API). Not executed here.
"use client";

import PaystackPop from "@paystack/inline-js";
import { apiFetch } from "@/lib/api";
import type { PlanKey } from "@/lib/paystack";

export default function PayInPopup({ plan, kind }: { plan: PlanKey; kind: "subscribe" | "pay" }) {
  async function start() {
    const { access_code, reference } = await apiFetch<{ access_code: string; reference: string }>(
      `/api/billing/paystack/${kind}/`, { method: "POST", body: { plan } });
    const popup = new PaystackPop();
    popup.resumeTransaction(access_code, {
      // The popup closing is not proof of payment. Always finish by asking the server (the callback page does).
      onSuccess: () => window.location.assign(`/billing/callback?reference=${encodeURIComponent(reference)}`),
      onCancel: () => { /* the customer closed the popup: nothing to do, the pending payment simply expires */ },
    });
  }
  return <button onClick={start}>Pay with Paystack</button>;
}
