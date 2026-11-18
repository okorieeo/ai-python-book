// mobile/billing.ts: the app reads the plan from YOUR server and starts payments there. Not executed here.
import { apiFetch } from "./api";

export type Status = { paid: boolean; tier: string; reason: string; until: number | null; card_last4: string };
export const getStatus = () => apiFetch<Status>("/api/billing/paystack/status/");

// Returns the Paystack checkout URL for PaystackCheckout. Use it only for what the store rules allow (37.10).
export async function startPayment(plan: string, kind: "pay" | "subscribe"): Promise<string> {
  const { authorization_url } = await apiFetch<{ authorization_url: string }>(
    `/api/billing/paystack/${kind}/`, { method: "POST", body: { plan } });
  return authorization_url;
}
