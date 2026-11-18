// lib/billing.ts: typed calls to the Django billing API. apiFetch is the authenticated fetch
// wrapper from the earlier frontend chapters (it adds the token and handles 401). Not executed here.
import { apiFetch } from "@/lib/api";

export type PlanKey = "pro_monthly" | "pro_yearly" | "team_monthly" | "credits_100";

export interface BillingStatus {
  paid: boolean;
  tier: "free" | "pro" | "team";
  reason: string;
  until: number | null;     // unix seconds
  status: string | null;
  credits: number;
}

export const getStatus = () => apiFetch<BillingStatus>("/api/billing/status/");

export async function startCheckout(plan: PlanKey): Promise<void> {
  const { url } = await apiFetch<{ url: string }>("/api/billing/checkout/", { method: "POST", body: { plan } });
  window.location.assign(url);          // the hosted Checkout page: Stripe.js is not even needed
}

export async function openPortal(): Promise<void> {
  const { url } = await apiFetch<{ url: string }>("/api/billing/portal/", { method: "POST" });
  window.location.assign(url);
}

export const syncCheckout = (sessionId: string) =>
  apiFetch<{ paid: boolean; tier: string; credits: number }>("/api/billing/sync/", {
    method: "POST",
    body: { session_id: sessionId },
  });

export const cancelSubscription = () => apiFetch("/api/billing/cancel/", { method: "POST", body: {} });
export const resumeSubscription = () => apiFetch("/api/billing/resume/", { method: "POST", body: {} });
