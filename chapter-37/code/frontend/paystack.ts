// lib/paystack.ts: typed calls to the Django billing API. apiFetch is the authenticated fetch wrapper from
// the earlier frontend chapters. Not executed here.
import { apiFetch } from "@/lib/api";

export type PlanKey = "pro_monthly_ngn" | "pro_yearly_ngn" | "team_monthly_ngn" | "pro_monthly_usd" | "credits_100";

export interface BillingStatus {
  paid: boolean;
  tier: "free" | "pro" | "team";
  reason: string;
  until: number | null;         // unix seconds
  status: string | null;
  card_last4: string;
  switching_to: PlanKey | null;
  credits: number;
}

interface Started { reference: string; authorization_url: string; access_code: string }

export const getStatus = () => apiFetch<BillingStatus>("/api/billing/paystack/status/");

/** Sends the browser to Paystack's checkout page. The server decides the amount from the plan key. */
export async function pay(plan: PlanKey, kind: "subscribe" | "pay"): Promise<void> {
  const res = await apiFetch<Started>(`/api/billing/paystack/${kind}/`, { method: "POST", body: { plan } });
  window.location.assign(res.authorization_url);
}

/** Called by the callback page. Never trusts the URL: the server asks Paystack and compares the amount. */
export const verify = (reference: string) =>
  apiFetch<{ status: string; paid: boolean; tier: string; credits: number }>("/api/billing/paystack/verify/", {
    method: "POST",
    body: { reference },
  });

export const cancelSubscription = () => apiFetch("/api/billing/paystack/cancel/", { method: "POST", body: {} });
export const resumeSubscription = () => apiFetch("/api/billing/paystack/resume/", { method: "POST", body: {} });
export const changePlan = (plan: PlanKey) => apiFetch("/api/billing/paystack/change-plan/", { method: "POST", body: { plan } });

export async function updateCard(): Promise<void> {
  const { url } = await apiFetch<{ url: string }>("/api/billing/paystack/card-link/", { method: "POST", body: {} });
  window.location.assign(url);   // a Paystack-hosted page where the customer replaces the card
}

export const formatMoney = (kobo: number, currency: string) =>
  new Intl.NumberFormat("en-NG", { style: "currency", currency }).format(kobo / 100);   // display only, never to compute
