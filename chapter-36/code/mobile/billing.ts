// mobile/billing.ts: the mobile app reads the plan from YOUR server. Not executed here.
import * as Linking from "expo-linking";
import { apiFetch } from "./api";

export type Status = { paid: boolean; tier: string; reason: string; until: number | null };
export const getStatus = () => apiFetch<Status>("/api/billing/status/");

// Opens the customer portal in the system browser (change card, see invoices, cancel).
// Managing an existing subscription is fine on both stores.
export async function manageSubscription() {
  const { url } = await apiFetch<{ url: string }>("/api/billing/portal/", { method: "POST" });
  await Linking.openURL(url);
}
